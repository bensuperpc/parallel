import secrets

from fastapi import Depends, HTTPException, Request
from fastapi.security import APIKeyHeader
from loguru import logger
from starlette.status import HTTP_403_FORBIDDEN

from api.config import get_api_settings

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def require_api_key(request: Request, api_key: str = Depends(_api_key_header)) -> str:
    settings = get_api_settings()
    logger.debug("Authenticating request to {}", request.url.path)
    if not secrets.compare_digest(api_key or "", settings.api_key):
        logger.warning("Forbidden access from {}: API key is missing or invalid", request.client.host if request.client else "unknown")
        raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="Forbidden access")
    return api_key
