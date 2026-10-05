from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GP_", env_file=".env", extra="ignore")

    app_name: str = "GreenPlot API"
    environment: str = "development"
    api_prefix: str = "/api/v1"

    database_url: str = "sqlite:///./greenplot.db"

    # Auth
    secret_key: str = "change-me-in-production-please-32b+"
    access_token_minutes: int = 30
    refresh_token_days: int = 14
    invite_token_hours: int = 72

    # CORS (comma separated)
    cors_origins: str = "http://localhost:3000"

    # Media storage: "local" or "s3"
    storage_backend: str = "local"
    local_storage_path: str = "./storage"
    public_base_url: str = "http://localhost:8000"
    s3_bucket: str = "greenplot-media"
    s3_endpoint_url: str | None = None
    s3_region: str = "auto"
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    signed_url_seconds: int = 300

    # Media limits (open questions 13-16: initial planning values)
    max_image_bytes: int = 15 * 1024 * 1024
    max_video_bytes: int = 100 * 1024 * 1024
    max_document_bytes: int = 20 * 1024 * 1024
    max_photos_per_task: int = 30
    routine_media_retention_days: int = 90
    incident_media_retention_days: int = 365 * 3

    # Rate limiting
    login_rate_per_minute: int = 10
    api_rate_per_minute: int = 600

    # Payments (Razorpay-compatible webhook signature)
    payment_provider: str = "razorpay"
    payment_webhook_secret: str = "whsec-dev"

    # Background worker inside the API process
    worker_enabled: bool = False
    worker_interval_seconds: int = 300

    whatsapp_number: str = "918105568225"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
