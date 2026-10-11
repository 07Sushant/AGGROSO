"""Application factory: middleware, CORS, error handlers, routers and startup tasks.

Runs as a single uvicorn worker on purpose: the AI probe cache, the circuit breaker and the log
ring buffer live in process memory.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import SQLAlchemyError

from app.agent.probe import ai_probe
from app.api import routes_auth, routes_health, routes_inputs, routes_ops
from app.config import Settings, get_settings
from app.db import init_engine, session_factory
from app.errors import register_error_handlers
from app.logging import RequestContextMiddleware, configure_logging, get_logger
from app.security import seed_demo_users

log = get_logger("app")


def _startup(settings: Settings) -> None:
    try:
        with session_factory()() as db:
            seed_demo_users(db, settings)
    except SQLAlchemyError as exc:
        # The app still starts; /api/health reports the database as down.
        log.error("startup.seed_failed", error=type(exc).__name__)
    if settings.llm_mode != "mock":
        ai_probe.refresh_in_background(settings)


def create_app(settings: Settings | None = None, *, init_db: bool = True) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_buffer_size)
    if init_db:
        init_engine(settings)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        log.info("app.starting", env=settings.app_env, version=settings.git_sha)
        _startup(settings)
        yield
        log.info("app.stopping")

    app = FastAPI(
        title="MigrateIQ API",
        version=settings.git_sha,
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )
    register_error_handlers(app)

    app.add_middleware(RequestContextMiddleware)
    # Added last, so it is the outermost layer and also decorates error responses.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_origin_regex=settings.cors_origin_regex or None,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID", "Idempotency-Key"],
        expose_headers=["X-Request-ID"],
        max_age=600,
    )

    for router in (
        routes_health.router,
        routes_auth.router,
        routes_inputs.router,
        routes_ops.router,
    ):
        app.include_router(router, prefix="/api")

    @app.get("/", include_in_schema=False)
    def root() -> dict[str, str]:
        return {"name": "MigrateIQ API", "docs": "/api/docs", "health": "/api/health"}

    return app


app = create_app()
