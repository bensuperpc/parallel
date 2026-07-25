from slowapi import Limiter
from slowapi.util import get_remote_address

from api.config import get_api_settings

_settings = get_api_settings()

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[_settings.rate_limit_default],
    storage_uri=_settings.valkey_url,
)
