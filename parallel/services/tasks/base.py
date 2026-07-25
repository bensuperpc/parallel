import os
import subprocess
from functools import lru_cache

import redis
from loguru import logger

from common.config import get_settings

RETRYABLE_TASK_KWARGS = dict(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=120,
    retry_jitter=True,
    max_retries=3,
)


class PoisonMessage(RuntimeError):
    """Raised once a task has been delivered more times than task_max_delivery_attempts."""


@lru_cache
def _attempts_redis() -> redis.Redis:
    settings = get_settings()
    return redis.Redis.from_url(settings.valkey_url)


def guard_delivery_attempts(task_id: str, max_attempts: int, log=logger) -> None:
    """Classic RabbitMQ queues (used here for their priority support) have no built-in
    delivery limit. A task that kills the worker process itself -- OOM, native segfault
    in ffmpeg/cwebp, hard time limit -- rather than raising a catchable Python exception
    gets redelivered by the broker (task_reject_on_worker_lost) forever: that path never
    touches Celery's own retries counter, which only increments on self.retry(), so
    autoretry_for's max_retries never sees it and never bounds it.

    This counts every execution attempt in Valkey regardless of cause. Once max_attempts
    is exceeded it raises a plain exception, which *is* caught by autoretry_for, so from
    then on the task is bounded by the normal max_retries=3 path and ends in a visible
    FAILURE instead of an unbounded redelivery loop that never surfaces anywhere."""
    settings = get_settings()
    key = f"task_attempts:{task_id}"
    r = _attempts_redis()
    attempts = r.incr(key)
    r.expire(key, settings.result_expires_seconds)
    if attempts > max_attempts:
        log.error("Task {} exceeded {} delivery attempts, failing permanently", task_id, max_attempts)
        raise PoisonMessage(f"exceeded {max_attempts} delivery attempts")


def clean_up_files(files: list[str], log=logger) -> None:
    for f in files:
        try:
            if os.path.exists(f):
                os.remove(f)
                log.info("Removed file: {}", f)
        except OSError as cleanup_error:
            log.error("Error during cleanup of {}: {}", f, cleanup_error)


def temp_path(task_id: str, s3_key: str) -> str:
    """Namespaces temp files under the task's own request id, so a redelivered/duplicate
    execution of the same task (at-least-once delivery + acks_late means this can happen)
    never collides with a still-running previous attempt on the same worker's filesystem."""
    settings = get_settings()
    task_dir = os.path.join(settings.temp_dir, task_id)
    os.makedirs(task_dir, exist_ok=True)
    return os.path.join(task_dir, os.path.basename(s3_key))


def run_encoder(command: list[str], log=logger) -> None:
    settings = get_settings()
    log.info("Running encoder command: {}", command)
    try:
        subprocess.run(command, check=True, timeout=settings.task_soft_time_limit_seconds)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"Encoder command timed out after {exc.timeout}s") from exc
