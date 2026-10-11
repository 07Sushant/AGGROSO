"""Structured JSON logging.

- structlog renders one JSON object per line to stdout.
- ``request_id`` and other request context are bound through contextvars by the middleware.
- A redaction processor masks secrets before anything is rendered.
- A ring buffer keeps the last N events for the in-app Logs view. Entries in the buffer are
  additionally stripped of provider/model identifiers, because the UI only knows engine aliases.
"""

from __future__ import annotations

import logging
import re
import sys
import threading
import time
import uuid
from collections import deque
from typing import Any

import structlog
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_SECRET_KEY_PARTS = ("key", "token", "password", "secret", "authorization", "cookie")
_SECRET_VALUE_PATTERNS = [
    re.compile(r"(postgres(?:ql)?(?:\+psycopg)?://[^:/\s]+:)[^@\s]+(@)"),
    re.compile(r"\bgsk_[A-Za-z0-9]{8,}"),
    re.compile(r"\bAIza[0-9A-Za-z_\-]{20,}"),
    re.compile(r"\bhf_[A-Za-z0-9]{20,}"),
    re.compile(r"(Bearer\s+)[A-Za-z0-9\-_\.]+"),
]
# Keys whose values must never reach the UI, even after redaction.
_INTERNAL_ONLY_KEYS = {"model_id", "model", "provider", "base_url"}
_PROVIDER_NAMES = re.compile(r"groq|gemini|qwen|google(?:apis)?|generativelanguage", re.I)

_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._\-]{1,64}$")


# Field names that merely contain a secret-looking word (counters and business identifiers).
_NON_SECRET_KEYS = {
    "tokens",
    "tokens_in",
    "tokens_out",
    "max_tokens",
    "token_type",
    "key",
    "dataset_key",
    "source_key",
    "idempotency_key",
}


def _is_secret_key(key: str) -> bool:
    lowered = key.lower()
    if lowered in _NON_SECRET_KEYS or lowered.endswith("_count"):
        return False
    return any(part in lowered for part in _SECRET_KEY_PARTS)


def _scrub_string(value: str) -> str:
    for pattern in _SECRET_VALUE_PATTERNS:
        if pattern.groups == 2:
            value = pattern.sub(r"\1***\2", value)
        elif pattern.groups == 1:
            value = pattern.sub(r"\1***", value)
        else:
            value = pattern.sub("***", value)
    return value


def redact(value: Any) -> Any:
    """Recursively mask secret-looking keys and values."""
    if isinstance(value, dict):
        return {
            k: ("***" if isinstance(k, str) and _is_secret_key(k) else redact(v))
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value]
    if isinstance(value, str):
        return _scrub_string(value)
    return value


def strip_provider_details(value: Any) -> Any:
    """Remove internal-only keys and provider names (UI vocabulary is primary/backup/mock)."""
    if isinstance(value, dict):
        return {
            k: strip_provider_details(v) for k, v in value.items() if k not in _INTERNAL_ONLY_KEYS
        }
    if isinstance(value, (list, tuple)):
        return [strip_provider_details(v) for v in value]
    if isinstance(value, str):
        return _PROVIDER_NAMES.sub("[provider]", value)
    return value


class RingBuffer:
    def __init__(self, size: int) -> None:
        self._items: deque[dict[str, Any]] = deque(maxlen=size)
        self._lock = threading.Lock()

    def append(self, item: dict[str, Any]) -> None:
        with self._lock:
            self._items.append(item)

    def query(
        self, request_id: str | None = None, event: str | None = None, limit: int = 200
    ) -> list[dict[str, Any]]:
        with self._lock:
            items = list(self._items)
        if request_id:
            items = [i for i in items if i.get("request_id") == request_id]
        if event:
            items = [i for i in items if event in str(i.get("event", ""))]
        return items[-limit:][::-1]  # newest first

    def clear(self) -> None:
        with self._lock:
            self._items.clear()


log_buffer = RingBuffer(1000)


def _redaction_processor(_logger: Any, _method: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    return redact(event_dict)


def _ring_buffer_processor(
    _logger: Any, _method: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    log_buffer.append(strip_provider_details(dict(event_dict)))
    return event_dict


def configure_logging(level: str = "INFO", buffer_size: int = 1000) -> None:
    global log_buffer
    if log_buffer._items.maxlen != buffer_size:
        log_buffer = RingBuffer(buffer_size)
    numeric_level = logging.getLevelName(level.upper())
    if not isinstance(numeric_level, int):
        numeric_level = logging.INFO
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            _logger_name_processor,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True, key="ts"),
            structlog.processors.format_exc_info,
            _redaction_processor,
            _ring_buffer_processor,
            structlog.processors.JSONRenderer(default=str),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=False,
    )
    # Route stdlib loggers (uvicorn, alembic, sqlalchemy warnings) through the same stdout.
    logging.basicConfig(level=numeric_level, stream=sys.stdout, format="%(message)s", force=True)


def get_logger(name: str = "app") -> Any:
    """``app`` for application events, ``ai`` for the AI workflow stream."""
    # Initial values keep the proxy lazy, so module-level loggers pick up configure_logging().
    # ("logger" itself is a reserved argument of structlog.get_logger, hence the rename step.)
    return structlog.get_logger(_logger_name=name)


def _logger_name_processor(
    _logger: Any, _method: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    name = event_dict.pop("_logger_name", None)
    if name is not None:
        event_dict["logger"] = name
    return event_dict


def new_request_id() -> str:
    return uuid.uuid4().hex


class RequestContextMiddleware:
    """Accepts or creates ``X-Request-ID``, binds it to the log context, echoes it on the
    response, writes one access line per request, and turns unhandled exceptions into the
    generic 500 envelope (details go to the log only)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.log = get_logger("app")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        incoming = headers.get("x-request-id", "")
        request_id = incoming if _REQUEST_ID_RE.match(incoming) else new_request_id()
        scope.setdefault("state", {})["request_id"] = request_id

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        started = time.perf_counter()
        status_holder = {"status": 500, "started": False}

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
                status_holder["started"] = True
                raw = [
                    (k, v) for k, v in message.get("headers", []) if k.lower() != b"x-request-id"
                ]
                raw.append((b"x-request-id", request_id.encode("latin-1")))
                message["headers"] = raw
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:  # noqa: BLE001 - last-resort handler; the error is logged in full
            self.log.exception("request.unhandled_error", path=scope.get("path"))
            if not status_holder["started"]:
                from app.errors import internal_error_response

                response = internal_error_response(request_id)
                await response(scope, receive, send_wrapper)
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 1)
            path = scope.get("path", "")
            if path not in ("/api/health/live",):
                self.log.info(
                    "http.request",
                    user=scope.get("state", {}).get("user"),
                    method=scope.get("method"),
                    path=path,
                    status=status_holder["status"],
                    duration_ms=duration_ms,
                )
            structlog.contextvars.clear_contextvars()
