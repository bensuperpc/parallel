from typing import Any

from pydantic import BaseModel


class UploadResponse(BaseModel):
    task_id: str
    s3_input_key: str
    s3_output_key: str
    priority: int


class TaskStatusResponse(BaseModel):
    task_id: str
    state: str
    error: str | None = None
    result: dict[str, Any] | None = None


class WorkerStatusResponse(BaseModel):
    worker_count: int
    all_workers_available: bool


class HealthResponse(BaseModel):
    status: str


class ClearStorageResponse(BaseModel):
    status: str
