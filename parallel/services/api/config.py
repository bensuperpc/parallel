from functools import lru_cache

from common.config import Settings


class ApiSettings(Settings):
    """API-only configuration, layered on top of the shared Settings. Kept in its
    own class (rather than folded into Settings) so the worker process -- which
    only ever instantiates Settings -- is never required to have API_KEY set."""

    api_key: str
    api_port: int = 5500
    rate_limit_default: str = "120/minute"
    rate_limit_upload: str = "20/minute"
    max_upload_size_bytes: int = 2 * 1024 * 1024 * 1024
    enable_docs: bool = False

    # --- Encoding defaults ---
    default_celery_task_priority: int = 5
    default_celery_routing_key: str = "video.all"
    default_compression_level: int = 9
    default_preset: int = 2
    default_crf: int = 16


@lru_cache
def get_api_settings() -> ApiSettings:
    return ApiSettings()
