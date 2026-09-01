"""Configuration handling, especially the URL shapes hosting providers hand out."""

import pytest

from app.config import Settings


@pytest.mark.parametrize(
    "provided,expected",
    [
        # Render/Fly/Heroku style -- SQLAlchemy 2 rejects this scheme outright.
        ("postgres://u:p@host:5432/db", "postgresql+psycopg2://u:p@host:5432/db"),
        # Valid but driver-less.
        ("postgresql://u:p@host:5432/db", "postgresql+psycopg2://u:p@host:5432/db"),
        # Already explicit -- left alone.
        ("postgresql+psycopg2://u:p@host:5432/db", "postgresql+psycopg2://u:p@host:5432/db"),
        # SQLite untouched.
        ("sqlite:///./emai.db", "sqlite:///./emai.db"),
    ],
)
def test_database_url_is_normalized_for_managed_postgres(provided, expected):
    assert Settings(database_url=provided).database_url == expected


def test_app_base_url_falls_back_to_the_api_origin():
    """Single-origin deployments only configure one URL; invite/reset links
    must still point somewhere real."""
    same_origin = Settings(public_base_url="https://sched.example.com/")
    assert same_origin.app_base_url == "https://sched.example.com"

    split = Settings(
        public_base_url="https://api.example.com",
        frontend_base_url="https://app.example.com/",
    )
    assert split.app_base_url == "https://app.example.com"
