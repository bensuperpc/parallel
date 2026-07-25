from celery import Celery
from kombu import Exchange, Queue

from common.config import get_settings

settings = get_settings()

celery_app = Celery("tasks", broker=settings.celery_broker_url, backend=settings.celery_result_backend)

video_exchange = Exchange(settings.celery_exchange, type="topic")

celery_app.conf.task_queues = (
    Queue(
        "video.high",
        exchange=video_exchange,
        routing_key="video.high",
        queue_arguments={"x-max-priority": 10, "x-queue-type": "classic"},
    ),
    Queue(
        "video.low",
        exchange=video_exchange,
        routing_key="video.low",
        queue_arguments={"x-max-priority": 10, "x-queue-type": "classic"},
    ),
    Queue(
        "video.all",
        exchange=video_exchange,
        routing_key="video.all",
        queue_arguments={"x-max-priority": 10, "x-queue-type": "classic"},
    ),
)

celery_app.conf.task_default_queue = "video.all"
celery_app.conf.task_default_exchange = settings.celery_exchange
celery_app.conf.task_default_exchange_type = "topic"
celery_app.conf.task_default_routing_key = "video.all"
celery_app.conf.broker_connection_retry_on_startup = True
celery_app.conf.broker_heartbeat = 60
celery_app.conf.broker_transport_options = {"confirm_publish": True}

celery_app.conf.task_acks_late = True
celery_app.conf.task_reject_on_worker_lost = True
celery_app.conf.worker_prefetch_multiplier = 1

celery_app.conf.result_expires = settings.result_expires_seconds

celery_app.conf.task_time_limit = settings.task_time_limit_seconds
celery_app.conf.task_soft_time_limit = settings.task_soft_time_limit_seconds

celery_app.control.mailbox.queue_exclusive = True
