from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, Depends, HTTPException
from loguru import logger

from api.config import get_api_settings
from api.schemas import ClearStorageResponse
from api.security import require_api_key
from common.storage import get_s3_client

router = APIRouter(prefix="/v1/admin", tags=["admin"])
settings = get_api_settings()


@router.post("/clear-storage", response_model=ClearStorageResponse)
async def clear_storage(_: str = Depends(require_api_key)) -> ClearStorageResponse:
    s3 = get_s3_client()
    try:
        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=settings.s3_bucket):
            if "Contents" in page:
                objects_to_delete = [{"Key": obj["Key"]} for obj in page["Contents"]]
                s3.delete_objects(Bucket=settings.s3_bucket, Delete={"Objects": objects_to_delete})
                logger.info("Deleted {} objects from S3 bucket {}", len(objects_to_delete), settings.s3_bucket)
        return ClearStorageResponse(status="Storage cleared")
    except (BotoCoreError, ClientError) as exc:
        logger.warning("Error clearing storage: {}", exc)
        raise HTTPException(status_code=503, detail="Failed to clear storage")
