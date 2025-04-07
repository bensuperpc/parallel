import os
import subprocess
import logging
import boto3
from boto3.s3.transfer import TransferConfig

from celery import Celery
from kombu import Exchange, Queue
from loguru import logger

broker_url = os.environ.get("CELERY_BROKER_URL", "amqp://user123:pass123@rabbitmq")

celery_exchange = os.environ.get("CELERY_EXCHANGE", "video")

celery_app = Celery('tasks', broker=broker_url)

video_exchange = Exchange(celery_exchange, type='topic')

celery_app.conf.task_queues = (
    Queue(
        'video.high',
        exchange=video_exchange,
        routing_key='video.high',
        queue_arguments={'x-max-priority': 10}
    ),
    Queue(
        'video.low',
        exchange=video_exchange,
        routing_key='video.low',
        queue_arguments={'x-max-priority': 10}
    ),
    Queue(
        'video.all',
        exchange=video_exchange,
        routing_key='video.all',
        queue_arguments={'x-max-priority': 10}
    )
)

celery_app.conf.task_default_queue = 'video.all'
celery_app.conf.task_default_exchange = 'video'
celery_app.conf.task_default_exchange_type = 'topic'
celery_app.conf.task_default_routing_key = 'video.all'

S3_ENDPOINT = os.environ.get("S3_ENDPOINT", "http://minio:9000")
S3_BUCKET = os.environ.get("S3_BUCKET", "videos")
MINIO_ACCESS_KEY = os.environ.get("MINIO_ACCESS_KEY", "minio")
MINIO_SECRET_KEY = os.environ.get("MINIO_SECRET_KEY", "minio123")

TEMP_DIR = os.environ.get("TEMP_DIR", "/tmp")

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

def clean_up_files(files):
    for f in files:
        try:
            if os.path.exists(f):
                os.remove(f)
                logger.info("Removed file: {}", f)
        except Exception as cleanup_error:
            logger.error("Error during cleanup of {}: {}", f, cleanup_error)

@celery_app.task
def encode_video_to_av1_task(s3_input_key : str, s3_output_key : str, preset : str = "2", crf : str = "16", option : str = "tune=0:enable-qm=1:qm-min=0:qm-max=8"):
    input_file = f"{TEMP_DIR}/{os.path.basename(s3_input_key)}"
    output_file = f"{TEMP_DIR}/{os.path.basename(s3_output_key)}"

    logger.info("Downloading file from S3: {}", s3_input_key)
    s3.download_file(S3_BUCKET, s3_input_key, input_file, Config=transfer_config)
    command = [
        "ffmpeg",
        "-i", input_file,
        "-y",
        "-loglevel", "warning",
        "-hide_banner",
        "-c:v", "libsvtav1",
        "-preset", preset,
        "-crf", crf,
        "-svtav1-params", option,
        "-c:a", "copy",
        "-c:s", "copy",
        "-map", "0",
        "-map_metadata", "0",
        "-map_chapters", "0",
        output_file
    ]
    logger.info("Video encoding will start with command: {}", command)
    try:
        subprocess.run(command, check=True)
        logger.info("Video encoding completed successfully")
    except subprocess.CalledProcessError as e:
        logger.error("Error during encoding: {}", e)

    s3.upload_file(output_file, S3_BUCKET, s3_output_key, Config=transfer_config)
    clean_up_files([input_file, output_file])

@celery_app.task
def encode_png_to_webp_task(s3_input_key : str, s3_output_key : str, compression_level : str = "9"):
    input_file = f"{TEMP_DIR}/{os.path.basename(s3_input_key)}"
    output_file = f"{TEMP_DIR}/{os.path.basename(s3_output_key)}"
    output_file = output_file.replace(".png", ".webp")

    logger.info("Downloading file from S3: {}", s3_input_key)
    s3.download_file(S3_BUCKET, s3_input_key, input_file, Config=transfer_config)

    command = [
        "cwebp",
        "-quiet",
        "-mt",
        "-metadata", "all",
        "-lossless",
        "-exact",
        "-z", compression_level,
        input_file,
        "-o", output_file
    ]
    logger.info("Image encoding will start with command: {}", command)
    try:
        subprocess.run(command, check=True)
        logger.info("Image encoding completed successfully")
    except subprocess.CalledProcessError as e:
        logger.error("Error during encoding: {}", e)

    s3.upload_file(output_file, S3_BUCKET, s3_output_key, Config=transfer_config)
    clean_up_files([input_file, output_file])
