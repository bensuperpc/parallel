from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    # --- Object storage (S3-compatible) ---
    s3_endpoint: str = "http://seaweedfs:9000"
    s3_bucket: str = "videos"
    s3_access_key: str = "app"
    s3_secret_key: str

    # --- RabbitMQ (Celery broker + management API) ---
    rabbitmq_host: str = "rabbitmq"
    rabbitmq_port: int = 5672
    rabbitmq_user: str = "app"
    rabbitmq_pass: str
    rabbitmq_mgmt_url: str = "http://rabbitmq:15672"

    # --- Valkey (Celery result backend) ---
    valkey_host: str = "valkey"
    valkey_port: int = 6379
    valkey_pass: str
    valkey_db: int = 0

    # --- Celery ---
    celery_exchange: str = "video"
    result_expires_seconds: int = 60 * 60 * 24
    task_time_limit_seconds: int = 30 * 60
    task_soft_time_limit_seconds: int = 25 * 60
    task_max_delivery_attempts: int = 8

    temp_dir: str = "/tmp"

    @property
    def celery_broker_url(self) -> str:
        return f"amqp://{self.rabbitmq_user}:{self.rabbitmq_pass}@{self.rabbitmq_host}:{self.rabbitmq_port}//"

    @property
    def valkey_url(self) -> str:
        return f"redis://:{self.valkey_pass}@{self.valkey_host}:{self.valkey_port}/{self.valkey_db}"

    @property
    def celery_result_backend(self) -> str:
        return self.valkey_url


@lru_cache
def get_settings() -> Settings:
    return Settings()
