"""Startup / health probe: one tiny call per engine, cached for ``LLM_PROBE_TTL_S`` seconds.

Results are reported with engine aliases only. A stale cache is served immediately while a
background thread refreshes it, so ``/api/health`` stays fast and quota use stays low.
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any

from openai import InternalServerError, OpenAIError, RateLimitError

from app.agent.engines import Engine, engines, make_client
from app.config import Settings, get_settings
from app.logging import get_logger

log = get_logger("ai")


def _probe_engine(engine: Engine, timeout_s: float) -> dict[str, Any]:
    if not engine.configured:
        return {"state": "not_configured", "latency_ms": None}
    started = time.perf_counter()
    client = make_client(engine, timeout_s)
    state, error = "down", None
    for attempt in range(2):  # same policy as the gateway: one retry on 429 / 5xx
        try:
            client.chat.completions.create(
                model=engine.model,
                messages=[{"role": "user", "content": "Reply with OK."}],
                max_tokens=1,
            )
            state, error = "ok", None
            break
        except (RateLimitError, InternalServerError) as exc:
            error = type(exc).__name__
            if attempt == 0:
                time.sleep(1)
        except OpenAIError as exc:
            error = type(exc).__name__
            break
    latency_ms = int((time.perf_counter() - started) * 1000)
    log.info("llm.probe", engine=engine.alias, state=state, latency_ms=latency_ms, error=error)
    return {"state": state, "latency_ms": latency_ms}


class AIProbe:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._result: dict[str, Any] | None = None
        self._checked_at = 0.0
        self._refreshing = False
        self._done = threading.Event()

    def reset(self) -> None:
        with self._lock:
            self._result, self._checked_at, self._refreshing = None, 0.0, False
            self._done = threading.Event()

    def refresh(self, settings: Settings | None = None) -> dict[str, Any]:
        settings = settings or get_settings()
        primary, backup = engines(settings)
        with ThreadPoolExecutor(max_workers=2) as pool:
            fp = pool.submit(_probe_engine, primary, settings.llm_probe_timeout_s)
            fb = pool.submit(_probe_engine, backup, settings.llm_probe_timeout_s)
            result = {"primary": fp.result(), "backup": fb.result()}
        result["checked_at"] = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._result, self._checked_at, self._refreshing = result, time.monotonic(), False
            self._done.set()
        return result

    def refresh_in_background(self, settings: Settings | None = None) -> None:
        with self._lock:
            if self._refreshing:
                return
            self._refreshing = True
        threading.Thread(target=self._safe_refresh, args=(settings,), daemon=True).start()

    def _safe_refresh(self, settings: Settings | None) -> None:
        try:
            self.refresh(settings)
        finally:
            with self._lock:
                self._refreshing = False

    def status(self, settings: Settings | None = None) -> dict[str, Any]:
        """Public AI status: ``primary`` | ``backup`` | ``down`` | ``mock``."""
        settings = settings or get_settings()
        if settings.llm_mode == "mock":
            return {"status": "mock", "primary": "mock", "backup": "mock", "checked_at": None}
        with self._lock:
            result, age = self._result, time.monotonic() - self._checked_at
            in_flight, done = self._refreshing, self._done
        if result is None and in_flight:
            # The startup probe is still running: wait for it instead of probing twice.
            done.wait(timeout=2 * settings.llm_probe_timeout_s + 5)
            with self._lock:
                result, age = self._result, time.monotonic() - self._checked_at
        if result is None:
            result = self.refresh(settings)
        elif age > settings.llm_probe_ttl_s:
            self.refresh_in_background(settings)
        return summarise(result, force_backup=settings.force_backup)


def summarise(result: dict[str, Any], *, force_backup: bool = False) -> dict[str, Any]:
    primary_ok = result["primary"]["state"] == "ok" and not force_backup
    backup_ok = result["backup"]["state"] == "ok"
    status = "primary" if primary_ok else "backup" if backup_ok else "down"
    return {
        "status": status,
        "primary": result["primary"]["state"],
        "backup": result["backup"]["state"],
        "checked_at": result.get("checked_at"),
    }


ai_probe = AIProbe()
