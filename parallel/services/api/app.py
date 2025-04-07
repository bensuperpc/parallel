import os
import uuid
import logging
import boto3
from boto3.s3.transfer import TransferConfig
from functools import wraps
from flask import Flask, request, jsonify, send_file, abort
from tasks import encode_video_task, encode_png_to_webp_task, encode_video_to_av1_task, celery_app
from loguru import logger

app = Flask(__name__)

S3_ENDPOINT = os.environ.get("S3_ENDPOINT", "http://minio:9000")
S3_BUCKET = os.environ.get("S3_BUCKET", "videos")
MINIO_ACCESS_KEY = os.environ.get("MINIO_ACCESS_KEY", "minio")
MINIO_SECRET_KEY = os.environ.get("MINIO_SECRET_KEY", "minio123")

API_KEY = os.environ.get("API_KEY", "defaultkey")
API_PORT = os.environ.get("API_PORT", 5500)

def require_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        apikey = request.args.get("apikey")
        if not apikey or apikey != API_KEY:
            logger.warning("Forbidden access : API key is missing or invalid")
            return jsonify({"error": "Forbidden access"}), 403
        return f(*args, **kwargs)
    return decorated

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

@app.route('/clear_storage', methods=['GET'])
@require_api_key
def clear_storage():
    """Clear all files from S3 bucket"""
    try:
        paginator = s3.get_paginator('list_objects_v2')
        for page in paginator.paginate(Bucket=S3_BUCKET):
            if 'Contents' in page:
                objects_to_delete = [{"Key": obj["Key"]} for obj in page["Contents"]]
                s3.delete_objects(Bucket=S3_BUCKET, Delete={"Objects": objects_to_delete})
                logger.info("Deleted {} objects from S3 bucket {}", len(objects_to_delete), S3_BUCKET)
        return jsonify({"status": "Storage cleared"}), 200
    except Exception as e:
        logger.error("Error clearing storage: {}", e)
        return jsonify({"error": "Failed to clear storage"}), 500


@app.route('/upload', methods=['POST'])
@require_api_key
def upload():
    if 'file' not in request.files:
        return jsonify({"error": "File not found"}), 400
    file = request.files['file']
    if file.filename == "":
        return jsonify({"error": "File name is empty"}), 400

    priority = int(os.environ.get("DEFAULT_CELERY_TASK_PRIORITY", 5))
    if 'priority' in request.files:
        priority = int(request.form['priority'])
    if priority < 0 or priority > 10:
        return jsonify({"error": "Priority must be between 0 and 10"}), 400
    
    routing_key = os.environ.get("DEFAULT_CELERY_ROUTING_KEY", "video.all")
    if 'routing_key' in request.form:
        routing_key = request.form['routing_key']
    if routing_key not in ["video.high", "video.low", "video.all"]:
        return jsonify({"error": "Invalid routing key"}), 400

    file_id = str(uuid.uuid4())
    s3_input_key = f"input/{file_id}_{file.filename}"
    s3_output_key = f"output/{file_id}_encoded_{file.filename}"

    s3.upload_fileobj(file, S3_BUCKET, s3_input_key)
    logger.info("File {} upload under key {}", file.filename, s3_input_key, Config=transfer_config)
    
    task = None
    
    if (file.filename.endswith(".png") or file.filename.endswith(".PNG")):
            s3_output_key = s3_output_key.replace(".png", ".webp")
            task = encode_png_to_webp_task.apply_async(
            args=[s3_input_key, s3_output_key],
            priority=priority,
            routing_key=routing_key
        )
    else:
        # encode_video_to_av1_task
        task = encode_video_task.apply_async(
            args=[s3_input_key, s3_output_key],
            priority=priority,
            routing_key=routing_key
        )
    
    logger.info("Task {} launched with priority {}", task.id, priority)

    return jsonify({
        "task_id": task.id,
        "s3_input_key": s3_input_key,
        "s3_output_key": s3_output_key,
        "priority": priority
    }), 202

@app.route('/download', methods=['GET'])
@require_api_key
def download():
    s3_output_key = request.args.get('s3_output_key')
    if not s3_output_key:
        return jsonify({"error": "Parameter s3_output_key is missing"}), 400

    local_file = f"/tmp/{os.path.basename(s3_output_key)}"
    try:
        s3.download_file(S3_BUCKET, s3_output_key, local_file, Config=transfer_config)
    except Exception as e:
        logger.error("Error downloading file from S3: {}", e)
        return jsonify({"error": f"File not found in S3: {s3_output_key}"}), 404
    return send_file(local_file, as_attachment=True)

@app.route('/status', methods=['GET'])
@app.route('/status/api', methods=['GET'])
@require_api_key
def status():
    return jsonify({"status": "OK"}), 200

@app.route('/status/worker', methods=['GET'])
@require_api_key
def workers():
    inspector = celery_app.control.inspect(timeout=5)

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

    return jsonify({
        "worker_count": worker_count,
        "all_workers_available": all_available,
        "workers": workers_status
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True, port=API_PORT)
