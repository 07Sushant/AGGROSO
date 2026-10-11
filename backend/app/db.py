"""Engine and session handling.

Neon's pooled endpoint runs PgBouncer in transaction mode, so server-side prepared statements
are disabled (``prepare_threshold=None``). Neon also scales to zero, so stale pooled connections
are detected with ``pool_pre_ping``.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from sqlalchemy import Insert, Table, create_engine, event
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings, get_settings


def build_engine(url: str, *, for_tests: bool = False) -> Engine:
    if url.startswith("sqlite"):
        kwargs: dict[str, Any] = {"connect_args": {"check_same_thread": False}}
        if for_tests or url in ("sqlite://", "sqlite:///:memory:"):
            kwargs["poolclass"] = StaticPool
        engine = create_engine(url, **kwargs)

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_conn: Any, _record: Any) -> None:  # pragma: no cover - trivial
            # Let SQLAlchemy own BEGIN/COMMIT so SAVEPOINTs work with pysqlite.
            dbapi_conn.isolation_level = None
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

        @event.listens_for(engine, "begin")
        def _sqlite_begin(conn: Any) -> None:  # pragma: no cover - trivial
            conn.exec_driver_sql("BEGIN")

        return engine

    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        pool_recycle=300,
        connect_args={"prepare_threshold": None, "connect_timeout": 15},
    )


_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def init_engine(settings: Settings | None = None, *, for_tests: bool = False) -> Engine:
    global _engine, _SessionLocal
    settings = settings or get_settings()
    if _engine is not None:
        _engine.dispose()
    _engine = build_engine(settings.sqlalchemy_url, for_tests=for_tests)
    _SessionLocal = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)
    return _engine


def get_engine() -> Engine:
    if _engine is None:
        init_engine()
    assert _engine is not None
    return _engine


def session_factory() -> sessionmaker[Session]:
    if _SessionLocal is None:
        init_engine()
    assert _SessionLocal is not None
    return _SessionLocal


def insert_ignore(table: Table, dialect_name: str) -> Insert:
    """``INSERT ... ON CONFLICT DO NOTHING`` (no conflict target, so every unique key counts)."""
    if dialect_name == "postgresql":
        return pg_insert(table).on_conflict_do_nothing()
    if dialect_name == "sqlite":
        return sqlite_insert(table).on_conflict_do_nothing()
    raise NotImplementedError(f"insert_ignore is not implemented for {dialect_name}")


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one session per request, closed afterwards."""
    db = session_factory()()
    try:
        yield db
    finally:
        db.close()
