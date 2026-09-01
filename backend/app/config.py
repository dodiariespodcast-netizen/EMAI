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


@lru_cache
def get_settings() -> Settings:
    return Settings()
