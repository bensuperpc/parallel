import os
import uuid

from botocore.exceptions import BotoCoreError, ClientError
from celery.exceptions import CeleryError
from celery.result import AsyncResult
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from loguru import logger

from api.config import get_api_settings
from api.media_handlers import UploadParams, resolve_handler
from api.rate_limit import limiter
from api.schemas import TaskStatusResponse, UploadResponse
from api.security import require_api_key
from api.uploads import SizeLimitedFile, UploadTooLarge
from common.celery_app import celery_app
from common.storage import TRANSFER_CONFIG, get_s3_client

router = APIRouter(prefix="/v1", tags=["media"])
settings = get_api_settings()
s3 = get_s3_client()

_ROUTING_KEYS = frozenset({"video.high", "video.low", "video.all"})
_DOWNLOAD_CHUNK_SIZE = 8 * 1024 * 1024


@router.post("/upload", response_model=UploadResponse)
@limiter.limit(settings.rate_limit_upload)
async def upload(
    request: Request,
    file: UploadFile = File(...),
    priority: int = Query(default=settings.default_celery_task_priority, ge=0, le=10),
    routing_key: str = Query(default=settings.default_celery_routing_key),
    compression_level: int = Query(default=settings.default_compression_level, ge=0, le=9),
    preset: int = Query(default=settings.default_preset, ge=0, le=13),
    crf: int = Query(default=settings.default_crf, ge=0, le=63),
    _: str = Depends(require_api_key),
) -> UploadResponse:
    if routing_key not in _ROUTING_KEYS:
        logger.warning("Invalid routing key: {}", routing_key)
        raise HTTPException(status_code=400, detail="Invalid routing key")

    handler = resolve_handler(file.filename or "")
    if handler is None:
        logger.error("Unsupported file type: {}", file.filename)
        raise HTTPException(status_code=400, detail="Unsupported file type")

    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > settings.max_upload_size_bytes:
        logger.warning("Upload rejected, declared size {} exceeds limit {}", content_length, settings.max_upload_size_bytes)
        raise HTTPException(status_code=413, detail=f"File exceeds max upload size of {settings.max_upload_size_bytes} bytes")

    file_id = str(uuid.uuid4())
    s3_input_key = f"input/{file_id}_{file.filename}"
    output_name = f"{file_id}_encoded_{file.filename}"
    if handler.output_extension:
        output_name = os.path.splitext(output_name)[0] + handler.output_extension
    s3_output_key = f"output/{output_name}"

    try:
        s3.upload_fileobj(
            SizeLimitedFile(file.file, settings.max_upload_size_bytes),
            settings.s3_bucket,
            s3_input_key,
            Config=TRANSFER_CONFIG,
        )
    except UploadTooLarge:
        logger.warning("Upload rejected, stream exceeded limit of {} bytes", settings.max_upload_size_bytes)
        raise HTTPException(status_code=413, detail=f"File exceeds max upload size of {settings.max_upload_size_bytes} bytes")
    except (BotoCoreError, ClientError) as exc:
        logger.error("Storage backend error while uploading: {}", exc)
        raise HTTPException(status_code=503, detail="Storage backend unavailable")
    logger.info("File {} uploaded under key {}", file.filename, s3_input_key)

    args = [s3_input_key, s3_output_key, *handler.build_args(UploadParams(compression_level, preset, crf))]
    try:
        task = celery_app.send_task(handler.task_name, args=args, priority=priority, routing_key=routing_key)
    except CeleryError as exc:
        logger.error("Failed to enqueue task, rolling back upload: {}", exc)
        s3.delete_object(Bucket=settings.s3_bucket, Key=s3_input_key)
        raise HTTPException(status_code=503, detail="Task queue unavailable")

    logger.info("Task {} launched with priority {}", task.id, priority)
    return UploadResponse(task_id=task.id, s3_input_key=s3_input_key, s3_output_key=s3_output_key, priority=priority)


@router.get("/tasks/{task_id}", response_model=TaskStatusResponse)
async def task_status(task_id: str, _: str = Depends(require_api_key)) -> TaskStatusResponse:
    try:
        result = AsyncResult(task_id, app=celery_app)
        state = result.state
        response = TaskStatusResponse(task_id=task_id, state=state)
        if state == "FAILURE":
            response.error = str(result.result)
        elif state == "SUCCESS":
            response.result = result.result
        return response
    except Exception as exc:
        logger.error("Failed to read task status from result backend: {}", exc)
        raise HTTPException(status_code=503, detail="Result backend unavailable")


@router.get("/tasks/{task_id}/download")
async def download_task_result(task_id: str, _: str = Depends(require_api_key)):
    try:
        result = AsyncResult(task_id, app=celery_app)
        state = result.state
        task_result = result.result
    except Exception as exc:
        logger.error("Failed to read task result from backend: {}", exc)
        raise HTTPException(status_code=503, detail="Result backend unavailable")

    if state != "SUCCESS":
        raise HTTPException(status_code=409, detail=f"Task is not finished successfully (state: {state})")

    s3_output_key: str | None = None
    if isinstance(task_result, dict):
        s3_output_key = task_result.get("s3_output_key")
    if not s3_output_key or not s3_output_key.startswith("output/"):
        logger.error("Task {} succeeded without a valid output key: {}", task_id, task_result)
        raise HTTPException(status_code=500, detail="Task has no downloadable output")

    try:
        s3_object = s3.get_object(Bucket=settings.s3_bucket, Key=s3_output_key)
    except (BotoCoreError, ClientError) as exc:
        logger.error("Error fetching object from S3: {}", exc)
        raise HTTPException(status_code=404, detail="Output file not found in storage")

    filename = os.path.basename(s3_output_key)
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    if "ContentLength" in s3_object:
        headers["Content-Length"] = str(s3_object["ContentLength"])
    return StreamingResponse(
        _iter_s3_body(s3_object["Body"]),
        media_type=s3_object.get("ContentType", "application/octet-stream"),
        headers=headers,
    )


def _iter_s3_body(body, chunk_size: int = _DOWNLOAD_CHUNK_SIZE):
    try:
        while chunk := body.read(chunk_size):
            yield chunk
    finally:
        body.close()
