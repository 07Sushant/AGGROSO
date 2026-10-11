from __future__ import annotations

import time

from fastapi import APIRouter
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.agent.probe import ai_probe
from app.config import get_settings
from app.db import get_engine
from app.logging import get_logger
from app.schemas.api import AiHealth, ConfigResponse, DbHealth, HealthResponse, LiveResponse
from app.security import DEMO_USERS

router = APIRouter(tags=["health"])
log = get_logger("app")


@router.get("/health/live", response_model=LiveResponse)
def live() -> LiveResponse:
    """Liveness only: no database or AI calls (used by uptime pingers)."""
    return LiveResponse()


def _check_db() -> DbHealth:
    started = time.perf_counter()
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        log.warning("health.db_down", error=type(exc).__name__)
        return DbHealth(status="down")
    return DbHealth(status="ok", latency_ms=int((time.perf_counter() - started) * 1000))


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    settings = get_settings()
    db = _check_db()
    ai = AiHealth(**ai_probe.status(settings))
    healthy = db.status == "ok" and ai.status in ("primary", "mock")
    return HealthResponse(
        status="ok" if healthy else "degraded",
        version=settings.git_sha,
        env=settings.app_env,
        db=db,
        ai=ai,
    )


@router.get("/config", response_model=ConfigResponse)
def config() -> ConfigResponse:
    settings = get_settings()
    return ConfigResponse(
        app_env=settings.app_env,
        version=settings.git_sha,
        max_source_records=settings.max_source_records,
        fault_injection_enabled=settings.fault_injection_enabled,
        llm_mode="mock" if settings.llm_mode == "mock" else "live",
        demo_accounts=[{"username": u, "role": r} for u, r in DEMO_USERS],
    )
