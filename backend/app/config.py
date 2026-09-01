"""Application configuration, loaded from environment variables (.env supported)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "EMAI Scheduler"
    environment: str = "development"

    # Storage. Defaults to a local SQLite file so the project runs with zero setup;
    # point DATABASE_URL at Postgres for anything beyond a single dev machine.
    database_url: str = "sqlite:///./emai_scheduler.db"

    # Auth
    secret_key: str = "CHANGE_ME_IN_PRODUCTION"
    access_token_expire_minutes: int = 60 * 12
    jwt_algorithm: str = "HS256"

    # AI layer (optional). Natural-language request parsing and schedule
    # explanations degrade gracefully to rule-based fallbacks when unset.
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-5"

    # Solver defaults
    solver_time_limit_seconds: float = 30.0

    cors_origins: list[str] = ["*"]

    # OAuth "Sign in with ___" (ID-token flow: the frontend obtains an ID
    # token from the provider's SDK and hands it to us to verify). Each is
    # independently optional -- /auth/oauth/* returns a clear error for a
    # provider whose client id isn't configured rather than failing at import.
    google_client_id: str | None = None
    microsoft_client_id: str | None = None

    # Outbound email (optional). Falls back to logging the message instead of
    # sending when unset, so the app runs without an email provider configured.
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_use_tls: bool = True
    email_from_address: str = "no-reply@emai-scheduler.example.com"
    email_from_name: str = "EMAI Scheduler"

    # Public base URL of this API, used to build links in emails and the
    # per-physician ICS calendar feed URL returned by the API.
    public_base_url: str = "http://localhost:8000"

    frontend_base_url: str = "http://localhost:5173"


@lru_cache
def get_settings() -> Settings:
    return Settings()
