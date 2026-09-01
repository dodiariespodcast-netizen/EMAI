import os
import tempfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("SECRET_KEY", "test-secret")
# The suite logs in far more often than a person would; leave the limiter off
# by default and exercise it explicitly in test_rate_limit.py.
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")

    # config/database read env vars at import time via lru_cache'd Settings,
    # so make sure each test gets a fresh module state pointed at its own DB.
    from app.config import get_settings

    get_settings.cache_clear()

    import app.database as database_module

    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    database_module.engine = engine
    database_module.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    from app.main import app

    with TestClient(app) as c:
        yield c

    get_settings.cache_clear()
