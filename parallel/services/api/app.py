import os
import uuid
from typing import IO
import boto3
import httpx
from boto3.s3.transfer import TransferConfig
from fastapi import FastAPI, File, UploadFile, Depends, Query, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import APIKeyHeader
from starlette.requests import Request
from starlette.status import HTTP_403_FORBIDDEN
from loguru import logger
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from celery.result import AsyncResult
from tasks import celery_app, encode_png_to_webp_task, encode_video_to_av1_task

# --- Config ---
S3_ENDPOINT = os.environ.get("S3_ENDPOINT", "http://seaweedfs:9000")
S3_BUCKET = os.environ.get("S3_BUCKET", "videos")
S3_ACCESS_KEY = os.environ.get("S3_ACCESS_KEY", "minio")
S3_SECRET_KEY = os.environ.get("S3_SECRET_KEY", "minio123")

API_KEY = os.environ.get("API_KEY", "defaultkey")
API_PORT = int(os.environ.get("API_PORT", 5500))

RABBITMQ_MGMT_URL = os.environ.get("RABBITMQ_MGMT_URL", "http://rabbitmq:15672")
RABBITMQ_USER = os.environ.get("RABBITMQ_USER", "user123")
RABBITMQ_PASS = os.environ.get("RABBITMQ_PASS", "pass123")

RATE_LIMIT_DEFAULT = os.environ.get("API_RATE_LIMIT_DEFAULT", "120/minute")
RATE_LIMIT_UPLOAD = os.environ.get("API_RATE_LIMIT_UPLOAD", "20/minute")

MAX_UPLOAD_SIZE_BYTES = int(os.environ.get("MAX_UPLOAD_SIZE_BYTES", 2 * 1024 * 1024 * 1024))

_TASK_QUEUE_NAMES = frozenset({"video.high", "video.low", "video.all"})

# --- Init ---
app = FastAPI(title="Encoding API")

limiter = Limiter(key_func=get_remote_address, default_limits=[RATE_LIMIT_DEFAULT])
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

s3 = boto3.client(
    "s3",
    endpoint_url=S3_ENDPOINT,
    aws_access_key_id=S3_ACCESS_KEY,
    aws_secret_access_key=S3_SECRET_KEY,
    region_name="us-east-1"
)

transfer_config = TransferConfig(
    multipart_threshold=20 * 1024 * 1024,
    multipart_chunksize=20 * 1024 * 1024,
    max_concurrency=10,
)

try:
    s3.create_bucket(Bucket=S3_BUCKET)
except Exception as e:
    logger.info("Bucket {} already exists or error: {}", S3_BUCKET, e)

class UploadTooLarge(Exception):
    pass

class SizeLimitedFile:
    """Wraps an upload's file object so streaming to S3 aborts once max_bytes is exceeded."""
    def __init__(self, fileobj: IO[bytes], max_bytes: int):
        self._fileobj = fileobj
        self._max_bytes = max_bytes
        self._read_bytes = 0

    def read(self, size: int = -1) -> bytes:
        chunk: bytes = self._fileobj.read(size)
        self._read_bytes += len(chunk)
        if self._read_bytes > self._max_bytes:
            raise UploadTooLarge()
        return chunk

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def require_api_key(
    request: Request,
    apikey_header: str = Depends(api_key_header)
):
    logger.debug("Authenticating request to {}", request.url.path)

    if apikey_header != API_KEY:
        logger.warning("Forbidden access: API key is missing or invalid")
        raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="Forbidden access")
    return apikey_header

# --- Routes ---

@app.get("/clear_storage")
async def clear_storage(_: str = Depends(require_api_key)):
    try:
        paginator = s3.get_paginator('list_objects_v2')
        for page in paginator.paginate(Bucket=S3_BUCKET):
            if 'Contents' in page:
                objects_to_delete = [{"Key": obj["Key"]} for obj in page["Contents"]]
                s3.delete_objects(Bucket=S3_BUCKET, Delete={"Objects": objects_to_delete})
                logger.info("Deleted {} objects from S3 bucket {}", len(objects_to_delete), S3_BUCKET)
        return {"status": "Storage cleared"}
    except Exception as e:
        logger.warning("Error clearing storage: {}", e)
        raise HTTPException(status_code=500, detail="Failed to clear storage")

@app.post("/upload")
@limiter.limit(RATE_LIMIT_UPLOAD)
async def upload(
    request: Request,
    file: UploadFile = File(...),
    priority: int = Query(default=int(os.environ.get("DEFAULT_CELERY_TASK_PRIORITY", 5)), ge=0, le=10),
    routing_key: str = Query(default=os.environ.get("DEFAULT_CELERY_ROUTING_KEY", "video.all")),
    compression_level: int = Query(default=int(os.environ.get("DEFAULT_COMPRESSION_LEVEL", 9)), ge=0, le=9),
    preset: int = Query(default=int(os.environ.get("DEFAULT_PRESET", 2)), ge=0, le=13),
    crf: int = Query(default=int(os.environ.get("DEFAULT_CRF", 2)), ge=0, le=63),
    _: str = Depends(require_api_key)
):
    if routing_key not in ["video.high", "video.low", "video.all"]:
        logger.warning("Invalid routing key: {}", routing_key)
        raise HTTPException(status_code=400, detail="Invalid routing key")

    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > MAX_UPLOAD_SIZE_BYTES:
        logger.warning("Upload rejected, declared size {} exceeds limit {}", content_length, MAX_UPLOAD_SIZE_BYTES)
        raise HTTPException(status_code=413, detail=f"File exceeds max upload size of {MAX_UPLOAD_SIZE_BYTES} bytes")

    file_id = str(uuid.uuid4())
    s3_input_key = f"input/{file_id}_{file.filename}"
    s3_output_key = f"output/{file_id}_encoded_{file.filename}"

    try:
        s3.upload_fileobj(SizeLimitedFile(file.file, MAX_UPLOAD_SIZE_BYTES), S3_BUCKET, s3_input_key, Config=transfer_config)
    except UploadTooLarge:
        logger.warning("Upload rejected, stream exceeded limit of {} bytes", MAX_UPLOAD_SIZE_BYTES)
        raise HTTPException(status_code=413, detail=f"File exceeds max upload size of {MAX_UPLOAD_SIZE_BYTES} bytes")
    logger.info("File {} uploaded under key {}", file.filename, s3_input_key)

    task = None
    if file.filename.lower().endswith(".png"):
        s3_output_key = s3_output_key.replace(".png", ".webp")
        task = encode_png_to_webp_task.apply_async(
            args=[s3_input_key, s3_output_key, str(compression_level)],
            priority=priority,
            routing_key=routing_key
        )
    elif file.filename.lower().endswith((".mp4", ".mkv", ".avi", ".mov")):
        task = encode_video_to_av1_task.apply_async(
            args=[s3_input_key, s3_output_key, str(preset), str(crf)],
            priority=priority,
            routing_key=routing_key
        )
    else:
        logger.error("Unsupported file type: {}", file.filename)
        s3.delete_object(Bucket=S3_BUCKET, Key=s3_input_key)
        raise HTTPException(status_code=400, detail="Unsupported file type")

    logger.info("Task {} launched with priority {}", task.id, priority)
    return {
        "task_id": task.id,
        "s3_input_key": s3_input_key,
        "s3_output_key": s3_output_key,
        "priority": priority
    }

@app.get("/status/task/{task_id}")
async def task_status(task_id: str, _: str = Depends(require_api_key)):
    result = AsyncResult(task_id, app=celery_app)
    response = {"task_id": task_id, "state": result.state}
    if result.state == "FAILURE":
        response["error"] = str(result.result)
    elif result.state == "SUCCESS":
        response["result"] = result.result
    return response

@app.get("/download")
async def download(s3_output_key: str = Query(...), _: str = Depends(require_api_key)):
    local_file = f"/tmp/{os.path.basename(s3_output_key)}"
    try:
        s3.download_file(S3_BUCKET, s3_output_key, local_file, Config=transfer_config)
    except Exception as e:
        logger.error("Error downloading file from S3: {}", e)
        raise HTTPException(status_code=404, detail=f"File not found in S3: {s3_output_key}")
    return FileResponse(local_file, filename=os.path.basename(local_file))

@app.get("/status")
@app.get("/status/api")
async def status(_: str = Depends(require_api_key)):
    return {"status": "OK"}

@app.get("/status/worker")
async def workers(_: str = Depends(require_api_key)):
    try:
        async with httpx.AsyncClient() as client:
            consumers_resp = await client.get(
                f"{RABBITMQ_MGMT_URL}/api/consumers/%2F",
                auth=(RABBITMQ_USER, RABBITMQ_PASS),
                timeout=5.0,
            )
            consumers_resp.raise_for_status()
            queues_resp = await client.get(
                f"{RABBITMQ_MGMT_URL}/api/queues/%2F",
                auth=(RABBITMQ_USER, RABBITMQ_PASS),
                timeout=5.0,
            )
            queues_resp.raise_for_status()
    except Exception as e:
        logger.error("Failed to query RabbitMQ management API: {}", e)
        raise HTTPException(status_code=503, detail="Unable to reach RabbitMQ management API")

    consumers = consumers_resp.json()
    queues = queues_resp.json()

    worker_connections: set[str] = set()
    for consumer in consumers:
        queue_name = consumer.get("queue", {}).get("name", "")
        if queue_name in _TASK_QUEUE_NAMES:
            conn_name = consumer.get("channel_details", {}).get("connection_name", "")
            if conn_name:
                worker_connections.add(conn_name)

    worker_count = len(worker_connections)

    total_unacked = sum(
        q.get("messages_unacknowledged", 0)
        for q in queues
        if q.get("name") in _TASK_QUEUE_NAMES
    )
    total_ready = sum(
        q.get("messages_ready", 0)
        for q in queues
        if q.get("name") in _TASK_QUEUE_NAMES
    )
    all_available = (total_unacked == 0) and (total_ready == 0)

    return {
        "worker_count": worker_count,
        "all_workers_available": all_available,
    }
