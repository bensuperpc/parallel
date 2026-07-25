import httpx
from fastapi import APIRouter, Depends, HTTPException
from loguru import logger

from api.config import get_api_settings
from api.schemas import HealthResponse, WorkerStatusResponse
from api.security import require_api_key

router = APIRouter(prefix="/health", tags=["health"])
settings = get_api_settings()

_TASK_QUEUE_NAMES = frozenset({"video.high", "video.low", "video.all"})


@router.get("", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Unauthenticated liveness probe, used by the Docker healthcheck: it must not
    require a secret so orchestration tooling can call it without holding the API key."""
    return HealthResponse(status="OK")


@router.get("/workers", response_model=WorkerStatusResponse)
async def workers(_: str = Depends(require_api_key)) -> WorkerStatusResponse:
    try:
        async with httpx.AsyncClient() as client:
            consumers_resp = await client.get(
                f"{settings.rabbitmq_mgmt_url}/api/consumers/%2F",
                auth=(settings.rabbitmq_user, settings.rabbitmq_pass),
                timeout=5.0,
            )
            consumers_resp.raise_for_status()
            queues_resp = await client.get(
                f"{settings.rabbitmq_mgmt_url}/api/queues/%2F",
                auth=(settings.rabbitmq_user, settings.rabbitmq_pass),
                timeout=5.0,
            )
            queues_resp.raise_for_status()
    except Exception as exc:
        logger.error("Failed to query RabbitMQ management API: {}", exc)
        raise HTTPException(status_code=503, detail="Unable to reach RabbitMQ management API")

    consumers = consumers_resp.json()
    queues = queues_resp.json()

    worker_connections: set[str] = set()
    for consumer in consumers:
        queue_name = consumer.get("queue", {}).get("name", "")
        if queue_name in _TASK_QUEUE_NAMES:
            conn_name = consumer.get("channel_details", {}).get("connection_name", "")
            if conn_name:
                worker_connections.add(conn_name)

    total_unacked = sum(q.get("messages_unacknowledged", 0) for q in queues if q.get("name") in _TASK_QUEUE_NAMES)
    total_ready = sum(q.get("messages_ready", 0) for q in queues if q.get("name") in _TASK_QUEUE_NAMES)

    return WorkerStatusResponse(
        worker_count=len(worker_connections),
        all_workers_available=(total_unacked == 0 and total_ready == 0),
    )
