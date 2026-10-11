"""LLM gateway (spec §7.1): one OpenAI-compatible code path for both engines.

- ``call(alias, ...)`` talks to one engine. A 429 / 5xx / malformed response is retried once on
  the same engine after ``LLM_RETRY_DELAY_S``; a timeout, connection or auth error fails at once.
  Failures raise ``EngineFailure``. The gateway never switches engines inside a conversation,
  because the backup needs its own tool-call history (thought signatures).
- ``chat(...)`` is the single-shot form with failover primary -> backup (used for vision).
- A circuit breaker skips the primary for 3 minutes after 3 failures within 2 minutes.
- Assistant messages are returned as ``message.model_dump(exclude_none=True)`` so callers can
  echo them unchanged (this preserves provider fields such as ``extra_content``).

Logs and results use the engine alias only; model ids and base URLs stay internal.
"""

from __future__ import annotations

import json
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

import openai

from app.agent.engines import Engine, engines, make_client, request_options
from app.config import Settings, get_settings
from app.domain.hashing import sha256_hex
from app.logging import get_logger

log = get_logger("ai")

RETRYABLE = frozenset({"rate_limited", "server_error", "malformed"})


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResult:
    engine: str
    content: str | None
    tool_calls: list[ToolCall]
    assistant_message: dict[str, Any]
    finish_reason: str | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0


class ProviderError(Exception):
    """A single failed request, classified. ``kind`` is part of the public vocabulary."""

    def __init__(self, kind: str, detail: str = "") -> None:
        super().__init__(kind)
        self.kind = kind
        self.detail = detail  # internal only (may name the provider); goes to the ai log


class EngineFailure(Exception):
    """An engine failed after the retry policy. ``reason`` is a ``ProviderError.kind``."""

    def __init__(self, engine: str, reason: str, latency_ms: int = 0) -> None:
        super().__init__(f"{engine} engine failed: {reason}")
        self.engine = engine
        self.reason = reason
        self.latency_ms = latency_ms


class LLMUnavailable(Exception):
    """Neither engine can serve the request."""

    def __init__(self, reasons: dict[str, str]) -> None:
        super().__init__("AI services are unavailable.")
        self.reasons = reasons


class ChatClient(Protocol):
    def complete(self, engine: Engine, request: dict[str, Any], timeout_s: float) -> LLMResult:
        """Send one chat request. Raises ``ProviderError``."""


class LiveClient:
    """The real client: the ``openai`` SDK pointed at the engine's base URL."""

    def complete(self, engine: Engine, request: dict[str, Any], timeout_s: float) -> LLMResult:
        client = make_client(engine, timeout_s)
        started = time.perf_counter()
        try:
            res = client.chat.completions.create(model=engine.model, **request)
        except openai.APITimeoutError as exc:
            raise ProviderError("timeout", str(exc)) from exc
        except openai.APIConnectionError as exc:
            raise ProviderError("connection", str(exc)) from exc
        except openai.RateLimitError as exc:
            raise ProviderError("rate_limited", str(exc)) from exc
        except (openai.AuthenticationError, openai.PermissionDeniedError) as exc:
            raise ProviderError("auth", str(exc)) from exc
        except openai.APIStatusError as exc:
            kind = "server_error" if exc.status_code >= 500 else "bad_request"
            raise ProviderError(kind, f"{exc.status_code}: {exc}") from exc
        except openai.OpenAIError as exc:
            raise ProviderError("client_error", str(exc)) from exc
        latency_ms = int((time.perf_counter() - started) * 1000)
        if not res.choices:
            raise ProviderError("malformed", "no choices in the response")
        choice = res.choices[0]
        message = choice.message
        calls: list[ToolCall] = []
        for tc in message.tool_calls or []:
            fn = getattr(tc, "function", None)
            if fn is None:
                raise ProviderError("malformed", "tool call without a function")
            calls.append(ToolCall(tc.id, fn.name, parse_arguments(fn.arguments)))
        usage = res.usage
        return LLMResult(
            engine=engine.alias,
            content=message.content,
            tool_calls=calls,
            assistant_message=message.model_dump(exclude_none=True),
            finish_reason=choice.finish_reason,
            tokens_in=getattr(usage, "prompt_tokens", 0) or 0,
            tokens_out=getattr(usage, "completion_tokens", 0) or 0,
            latency_ms=latency_ms,
        )


def parse_arguments(raw: str | None) -> dict[str, Any]:
    """Tool-call arguments must be a JSON object; anything else is a malformed response."""
    try:
        value = json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        raise ProviderError("malformed", "tool-call arguments are not valid JSON") from exc
    if not isinstance(value, dict):
        raise ProviderError("malformed", "tool-call arguments are not a JSON object")
    return value


class CircuitBreaker:
    """In memory (one uvicorn worker): ``threshold`` primary failures within ``window_s``
    open the circuit for ``cooldown_s``; then the primary is tried again."""

    def __init__(self, threshold: int = 3, window_s: float = 120.0, cooldown_s: float = 180.0,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.threshold, self.window_s, self.cooldown_s = threshold, window_s, cooldown_s
        self._clock = clock
        self._failures: deque[float] = deque()
        self._open_until = 0.0
        self._lock = threading.Lock()

    def record_failure(self) -> None:
        with self._lock:
            now = self._clock()
            self._failures.append(now)
            while self._failures and now - self._failures[0] > self.window_s:
                self._failures.popleft()
            if len(self._failures) >= self.threshold:
                self._open_until = now + self.cooldown_s
                self._failures.clear()
                log.warning("llm.circuit_opened", engine="primary", cooldown_s=self.cooldown_s)

    def record_success(self) -> None:
        with self._lock:
            self._failures.clear()

    def is_open(self) -> bool:
        with self._lock:
            return self._clock() < self._open_until

    def reset(self) -> None:
        with self._lock:
            self._failures.clear()
            self._open_until = 0.0


breaker = CircuitBreaker()


def prompt_hash(messages: list[dict[str, Any]]) -> str:
    return sha256_hex(messages)[:16]


@dataclass
class Gateway:
    client: ChatClient
    settings: Settings
    mock: bool = False
    _engines: dict[str, Engine] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._engines = {e.alias: e for e in engines(self.settings)}

    def engine(self, alias: str) -> Engine:
        return self._engines[alias]

    def configured(self, alias: str) -> bool:
        return self.mock or self._engines[alias].configured

    def primary_skip_reason(self) -> str | None:
        """Why the primary should not be used right now (None means: use it)."""
        if self.settings.force_backup:
            return "forced"
        if not self.configured("primary"):
            return "not_configured"
        if breaker.is_open():
            return "circuit_open"
        return None

    def timeout_for(self, alias: str) -> float:
        return self._engines[alias].timeout_s

    def call(
        self,
        alias: str,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: Any = None,
        response_format: dict[str, Any] | None = None,
        max_completion_tokens: int,
        timeout_s: float | None = None,
        prompt_version: str | None = None,
    ) -> LLMResult:
        engine = self._engines[alias]
        if not self.configured(alias):
            raise EngineFailure(alias, "not_configured")
        request: dict[str, Any] = {
            "messages": messages,
            **request_options(engine, max_completion_tokens=max_completion_tokens),
        }
        if tools:
            request["tools"] = tools
            if tool_choice is not None:
                request["tool_choice"] = tool_choice
        if response_format is not None:
            request["response_format"] = response_format
        timeout = min(timeout_s or engine.timeout_s, engine.timeout_s)
        started = time.perf_counter()
        last_kind = "unknown"
        for attempt in (1, 2):
            log.info("llm.request", engine=alias, attempt=attempt, messages=len(messages),
                     tools=len(tools or []), prompt_hash=prompt_hash(messages),
                     prompt_version=prompt_version)
            try:
                result = self.client.complete(engine, request, timeout)
            except ProviderError as exc:
                last_kind = exc.kind
                log.warning("llm.error", engine=alias, attempt=attempt, reason=exc.kind,
                            detail=exc.detail[:300])
                if exc.kind in RETRYABLE and attempt == 1:
                    time.sleep(self.settings.llm_retry_delay_s)
                    continue
                break
            if alias == "primary":
                breaker.record_success()
            log.info("llm.response", engine=alias, latency_ms=result.latency_ms,
                     tokens_in=result.tokens_in, tokens_out=result.tokens_out,
                     finish_reason=result.finish_reason, tool_calls=len(result.tool_calls))
            return result
        if alias == "primary":
            breaker.record_failure()
        raise EngineFailure(alias, last_kind, int((time.perf_counter() - started) * 1000))

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        response_format: dict[str, Any] | None = None,
        max_completion_tokens: int,
        on_fallback: Callable[[str, str], None] | None = None,
    ) -> LLMResult:
        """Single-shot call with failover. ``on_fallback(from_reason, to_alias)`` is called when
        the backup takes over."""
        reasons: dict[str, str] = {}
        skip = self.primary_skip_reason()
        order = ["backup"] if skip else ["primary", "backup"]
        if skip:
            reasons["primary"] = skip
        for alias in order:
            if alias == "backup" and reasons and on_fallback is not None:
                on_fallback(reasons.get("primary", "unknown"), "backup")
                log.warning("llm.fallback", from_engine="primary", to_engine="backup",
                            reason=reasons.get("primary"))
            try:
                return self.call(alias, messages=messages, response_format=response_format,
                                 max_completion_tokens=max_completion_tokens)
            except EngineFailure as exc:
                reasons[alias] = exc.reason
        raise LLMUnavailable(reasons)


def get_gateway(settings: Settings | None = None) -> Gateway:
    settings = settings or get_settings()
    if settings.llm_mode == "mock":
        from app.agent.mock_llm import mock_client

        return Gateway(mock_client, settings, mock=True)
    return Gateway(LiveClient(), settings)
