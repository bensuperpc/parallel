from loguru import logger

from common.celery_app import celery_app
from common.config import get_settings
from common.storage import TRANSFER_CONFIG, get_s3_client
from common.task_names import ENCODE_PNG_TO_WEBP
from tasks.base import RETRYABLE_TASK_KWARGS, clean_up_files, guard_delivery_attempts, run_encoder, temp_path


@celery_app.task(name=ENCODE_PNG_TO_WEBP, **RETRYABLE_TASK_KWARGS)
def encode_png_to_webp_task(self, s3_input_key: str, s3_output_key: str, compression_level: str = "9"):
    log = logger.bind(task_id=self.request.id)
    settings = get_settings()
    guard_delivery_attempts(self.request.id, settings.task_max_delivery_attempts, log)
    s3 = get_s3_client()

    input_file = temp_path(self.request.id, s3_input_key)
    output_file = temp_path(self.request.id, s3_output_key.replace(".png", ".webp"))

    log.info("Downloading file from S3: {}", s3_input_key)
    s3.download_file(settings.s3_bucket, s3_input_key, input_file, Config=TRANSFER_CONFIG)

    command = [
        "cwebp",
        "-quiet",
        "-mt",
        "-metadata", "all",
        "-lossless",
        "-exact",
        "-z", compression_level,
        input_file,
        "-o", output_file,
    ]
    try:
        run_encoder(command, log)
    except Exception:
        clean_up_files([input_file, output_file], log)
        raise

    s3.upload_file(output_file, settings.s3_bucket, s3_output_key, Config=TRANSFER_CONFIG)
    clean_up_files([input_file, output_file], log)
    return {"s3_output_key": s3_output_key}
