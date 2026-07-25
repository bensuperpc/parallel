from functools import lru_cache

from boto3 import client as boto3_client
from boto3.s3.transfer import TransferConfig

from common.config import get_settings

TRANSFER_CONFIG = TransferConfig(
    multipart_threshold=20 * 1024 * 1024,
    multipart_chunksize=20 * 1024 * 1024,
    max_concurrency=10,
)


@lru_cache
def get_s3_client():
    settings = get_settings()
    return boto3_client(
        "s3",
        endpoint_url=settings.s3_endpoint,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name="us-east-1",
    )
