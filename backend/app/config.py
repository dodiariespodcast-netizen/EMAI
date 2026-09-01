"""Application configuration, loaded from environment variables (.env supported)."""
from functools import lru_cache

from pydantic import field_validator
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

    # Where the app is reachable from a browser, used for invite/reset email
    # links. Leave unset when the API serves the frontend itself -- links then
    # point at PUBLIC_BASE_URL, which is the same place.
    frontend_base_url: str | None = None

    # Directory holding the built frontend. Unset auto-detects a sibling
    # `frontend/dist`; point it somewhere explicit in a container. When there
    # is no build to serve, the process runs as a plain API.
    static_dir: str | None = None

    # Ops
    log_level: str = "INFO"
    rate_limit_enabled: bool = True

    @field_validator("database_url")
    @classmethod
    def _normalize_database_url(cls, value: str) -> str:
        """Accept the URL shapes hosting providers actually hand out.

        Render, Fly, Heroku and friends set DATABASE_URL to `postgres://...`,
        which SQLAlchemy 2 rejects outright, and `postgresql://...` without a
        driver. Rewriting here means an attached database just works instead
        of failing on first boot with an unhelpful dialect error.
        """
        if value.startswith("postgres://"):
            return "postgresql+psycopg2://" + value[len("postgres://") :]
        if value.startswith("postgresql://"):
            return "postgresql+psycopg2://" + value[len("postgresql://") :]
        return value

    @property
    def app_base_url(self) -> str:
        """The origin to build user-facing links from."""
        return (self.frontend_base_url or self.public_base_url).rstrip("/")


@lru_cache
def get_settings() -> Settings:
    return Settings()
