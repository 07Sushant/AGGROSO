"""Test setup: SQLite temp-file DB locally (Postgres in CI via TEST_DATABASE_URL), mock LLM mode.

Tests never touch Neon and never call a live model: the environment below overrides .env.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

_TMP_DIR = tempfile.mkdtemp(prefix="migrateiq-tests-")
_TEST_DB_URL = os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{Path(_TMP_DIR) / 'test.db'}"

os.environ.update(
    {
        "DATABASE_URL": _TEST_DB_URL,
        "DATABASE_URL_DIRECT": "",
        "GROQ_API_KEY": "",
        "GEMINI_API_KEY": "",
        "LLM_MODE": "mock",
        "APP_ENV": "test",
        "DEMO_PASSWORD": "migrateiq-demo",
        "JWT_SECRET": "test-only-jwt-secret-0123456789abcdef",
        "FAULT_INJECTION_ENABLED": "true",
        "AGENT_JOBS_INLINE": "true",
        "LLM_RETRY_DELAY_S": "0",
        "FORCE_BACKUP": "false",
        "AGENT_MODE": "full",
    }
)

from fastapi.testclient import TestClient  # noqa: E402

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.db import get_engine, init_engine  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import Base  # noqa: E402

DEMO_PASSWORD = "migrateiq-demo"
IS_POSTGRES = _TEST_DB_URL.startswith(("postgresql", "postgres"))


def pytest_collection_modifyitems(config, items):  # type: ignore[no-untyped-def]
    if IS_POSTGRES:
        return
    skip = pytest.mark.skip(reason="needs PostgreSQL (runs in CI)")
    for item in items:
        if "postgres" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def app():  # type: ignore[no-untyped-def]
    settings = get_settings()
    init_engine(settings, for_tests=True)
    engine = get_engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    application = create_app(settings, init_db=False)
    yield application
    if not IS_POSTGRES:
        # agent_runs <-> plan_versions reference each other; SQLite cannot drop such tables
        # with rows present while foreign keys are enforced.
        raw = engine.raw_connection()
        raw.driver_connection.execute("PRAGMA foreign_keys=OFF")
        raw.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture(scope="session")
def client(app) -> Iterator[TestClient]:  # type: ignore[no-untyped-def]
    with TestClient(app) as c:  # runs the lifespan (seeds demo users)
        yield c


def _login(client: TestClient, username: str) -> str:
    res = client.post("/api/auth/login", json={"username": username, "password": DEMO_PASSWORD})
    assert res.status_code == 200, res.text
    return res.json()["access_token"]


@pytest.fixture(scope="session")
def operator_headers(client: TestClient) -> dict[str, str]:
    return {"Authorization": f"Bearer {_login(client, 'operator')}"}


@pytest.fixture(scope="session")
def approver_headers(client: TestClient) -> dict[str, str]:
    return {"Authorization": f"Bearer {_login(client, 'approver')}"}
