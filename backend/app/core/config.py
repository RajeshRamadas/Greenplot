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

    # Account protection
    lockout_threshold: int = 5  # failed sign-ins before a temporary lock
    lockout_minutes: int = 15
    otp_minutes: int = 10  # one-time codes (phone sign-in, password reset, phone check)
    otp_max_attempts: int = 5
    otp_per_hour: int = 5  # codes sent per destination per hour
    mfa_token_minutes: int = 5
    mfa_required_roles: str = ""  # e.g. "super_admin,layout_admin": these roles must enrol in 2-step verification
    # Show one-time codes in API responses outside production, so demos work without SMS/WhatsApp/email.
    dev_show_codes: bool = True

    # Email (SMTP). Without a host, emails are only logged.
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str = "GreenPlot <no-reply@greenplot.in>"
    smtp_starttls: bool = True

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

    whatsapp_number: str = "918105568225"  # public contact number shown on the website

    # WhatsApp Business Cloud API (Meta). "log" only logs messages; "meta" sends them.
    whatsapp_provider: str = "log"
    whatsapp_api_url: str = "https://graph.facebook.com"
    whatsapp_api_version: str = "v21.0"
    whatsapp_phone_number_id: str | None = None
    whatsapp_access_token: str | None = None
    whatsapp_app_secret: str | None = None  # verifies X-Hub-Signature-256 on webhooks
    whatsapp_verify_token: str | None = None  # answers Meta's webhook subscription challenge
    whatsapp_template: str = "greenplot_update"  # approved utility template with {{1}} title and {{2}} body
    whatsapp_template_language: str = "en"
    whatsapp_otp_template: str = "greenplot_otp"  # approved Authentication template with a copy-code button

    # SMS via MSG91 Flow API with DLT-registered templates. "log" only logs; "msg91" sends.
    sms_provider: str = "log"
    msg91_api_url: str = "https://control.msg91.com/api/v5"
    msg91_authkey: str | None = None
    msg91_sender: str | None = None  # 6-letter DLT sender id (optional when set on the template)
    msg91_otp_template_id: str | None = None  # variables: ##otp##
    msg91_notify_template_id: str | None = None  # variables: ##title## ##body##
    msg91_link_template_id: str | None = None  # variables: ##title## ##link##
    msg91_var_max: int = 30  # DLT limit per variable
    msg91_webhook_token: str | None = None  # secret in the delivery-report URL
    default_country_code: str = "91"

    @property
    def mfa_roles(self) -> set[str]:
        return {r.strip() for r in self.mfa_required_roles.split(",") if r.strip()}

    @property
    def show_codes(self) -> bool:
        return self.dev_show_codes and self.environment != "production"

    @property
    def app_url(self) -> str:
        """Where people open the web app (links in invites and emails)."""
        return (self.cors_origin_list[0] if self.cors_origin_list else self.public_base_url).rstrip("/")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
