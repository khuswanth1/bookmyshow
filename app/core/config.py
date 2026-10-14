from functools import lru_cache
from pathlib import Path

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(ROOT / ".env", ROOT / "backend" / ".env"),
        extra="ignore",
    )

    env: str = "development"  # development | production | test
    database_url: str = "postgresql+psycopg://bms@localhost:54329/bookmyshow"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    frontend_url: str = "http://localhost:5173"

    # Auth
    jwt_secret: str = "dev-only-change-me-dev-only-change-me"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 30
    refresh_token_days: int = 7
    google_client_id: str = ""
    google_client_secret: str = ""
    # Must be listed under "Authorised redirect URIs" of the OAuth client. Defaults to the Vite/nginx-proxied API path.
    google_redirect_uri: str = ""

    # Razorpay (test mode keys are fine)
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""

    # Booking rules
    seat_lock_minutes: int = 8
    payment_window_minutes: int = 10
    max_seats_per_booking: int = 10
    convenience_fee_pct: float = 3.0
    gst_pct: float = 18.0
    cancellation_cutoff_hours: int = 2

    # Email (optional). Without SMTP_HOST, emails are logged and stored as notifications only.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    mail_from: str = "tickets@bookmyshow.example.com"

    # Seed
    admin_email: str = "admin@bookmyshow.example.com"
    admin_password: str = "Admin@12345"

    @field_validator("database_url")
    @classmethod
    def _driver(cls, v: str) -> str:
        if not v:
            return "postgresql+psycopg://postgres:2205@localhost:5432/bookmyshow"
        v = v.strip().strip("\"'").strip()
        # Accept plain postgres:// URLs from hosting providers
        if v.startswith("postgres://"):
            v = "postgresql://" + v[len("postgres://"):]
        if v.startswith("postgresql://"):
            v = "postgresql+psycopg://" + v[len("postgresql://"):]
        return v

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @model_validator(mode="after")
    def _redirect_default(self):
        if not self.google_redirect_uri:
            self.google_redirect_uri = self.frontend_url.rstrip("/") + "/api/v1/calendar/callback"
        return self

    @property
    def is_prod(self) -> bool:
        return self.env == "production"

    @property
    def razorpay_enabled(self) -> bool:
        return bool(self.razorpay_key_id and self.razorpay_key_secret)


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if s.is_prod and s.jwt_secret.startswith("dev-only"):
        raise RuntimeError("JWT_SECRET must be set in production")
    return s


settings = get_settings()
# Settings reloaded from .env
