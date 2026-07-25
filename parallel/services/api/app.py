from contextlib import asynccontextmanager

from botocore.exceptions import BotoCoreError, ClientError
from fastapi import FastAPI
from loguru import logger
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from api.config import get_api_settings
from api.rate_limit import limiter
from api.routers import admin, health, media
from common.storage import get_s3_client

settings = get_api_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    s3 = get_s3_client()
    try:
        s3.create_bucket(Bucket=settings.s3_bucket)
    except (BotoCoreError, ClientError) as exc:
        logger.info("Bucket {} already exists or error: {}", settings.s3_bucket, exc)
    yield


app = FastAPI(
    title="Encoding API",
    docs_url="/docs" if settings.enable_docs else None,
    redoc_url="/redoc" if settings.enable_docs else None,
    openapi_url="/openapi.json" if settings.enable_docs else None,
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.include_router(media.router)
app.include_router(health.router)
app.include_router(admin.router)
