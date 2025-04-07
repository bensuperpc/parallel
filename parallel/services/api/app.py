import os
import uuid
import boto3
from boto3.s3.transfer import TransferConfig
from fastapi import FastAPI, File, UploadFile, Depends, Query, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security.api_key import APIKeyQuery
from fastapi.security import APIKeyHeader
from starlette.requests import Request
from starlette.status import HTTP_403_FORBIDDEN
from loguru import logger
from tasks import encode_png_to_webp_task, encode_video_to_av1_task, celery_app

# --- Config ---
S3_ENDPOINT = os.environ.get("S3_ENDPOINT", "http://minio:9000")
S3_BUCKET = os.environ.get("S3_BUCKET", "videos")
MINIO_ACCESS_KEY = os.environ.get("MINIO_ACCESS_KEY", "minio")
MINIO_SECRET_KEY = os.environ.get("MINIO_SECRET_KEY", "minio123")

API_KEY = os.environ.get("API_KEY", "defaultkey")
API_PORT = int(os.environ.get("API_PORT", 5500))

# --- Init ---
app = FastAPI(title="Encoding API")

s3 = boto3.client(
    "s3",
    endpoint_url=S3_ENDPOINT,
    aws_access_key_id=MINIO_ACCESS_KEY,
    aws_secret_access_key=MINIO_SECRET_KEY,
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

# --- API Key dependency ---
api_key_query = APIKeyQuery(name="apikey", auto_error=False)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def require_api_key(
    apikey_query: str = Depends(api_key_query),
    apikey_header: str = Depends(api_key_header)
):
    if apikey_query and not apikey_header:
        logger.warning("Using deprecated API key query parameter")
        
    apikey = apikey_query or apikey_header
    if apikey != API_KEY:
        logger.warning("Forbidden access: API key is missing or invalid")
        raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="Forbidden access")
    return apikey

# --- Routes ---

@app.get("/download_script")
async def download_script(_: str = Depends(require_api_key)):
    script_path = os.path.join(os.path.dirname(__file__), "tasks.py")
    if not os.path.exists(script_path):
        logger.error("Script file not found: {}", script_path)
        raise HTTPException(status_code=404, detail="Script file not found")
    return FileResponse(script_path, filename="tasks.py")

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
async def upload(
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

    file_id = str(uuid.uuid4())
    s3_input_key = f"input/{file_id}_{file.filename}"
    s3_output_key = f"output/{file_id}_encoded_{file.filename}"

    s3.upload_fileobj(file.file, S3_BUCKET, s3_input_key, Config=transfer_config)
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
    inspector = celery_app.control.inspect(timeout=0.5)

    worker_pings = inspector.ping() or {}
    active_tasks = inspector.active() or {}
    reserved_tasks = inspector.reserved() or {}
    scheduled_tasks = inspector.scheduled() or {}

    worker_count = len(worker_pings)
    workers_status = {}
    all_available = True

    for worker in worker_pings:
        active = active_tasks.get(worker, [])
        reserved = reserved_tasks.get(worker, [])
        scheduled = scheduled_tasks.get(worker, [])

        is_busy = bool(active or reserved or scheduled)
        if is_busy:
            all_available = False

        workers_status[worker] = {
            "ping": "ok",
            "active_tasks": len(active),
            "reserved_tasks": len(reserved),
            "scheduled_tasks": len(scheduled),
            "status": "busy" if is_busy else "available"
        }

    return {
        "worker_count": worker_count,
        "all_workers_available": all_available,
        "workers": workers_status
    }
