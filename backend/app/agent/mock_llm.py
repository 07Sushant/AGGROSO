"""Mock LLM (``LLM_MODE=mock``, tests only). Same interface as the live client.

It returns scripted responses, and the runner replays them through the real tool dispatcher and
plan validator. Scripts are queued per engine alias; each item is one of:

- ``{"tool_calls": [{"name": ..., "arguments": {...} | "<raw json>"}], "content": ...}``
- ``{"content": "..."}`` (a plain text reply)
- ``{"error": "timeout" | "rate_limited" | "server_error" | "connection" | "auth" | ...}``
- a callable ``(engine_alias, request) -> item``

With nothing queued, a default responder inspects the schemas once, then submits the reference
plan (or returns a small schema extraction for JSON-mode vision requests). Every request is kept
in ``calls`` so tests can assert what each engine was sent.
"""

from __future__ import annotations

import copy
import itertools
import json
import threading
from collections import deque
from collections.abc import Callable
from typing import Any

from app.agent.engines import Engine
from app.agent.gateway import LLMResult, ProviderError, ToolCall, parse_arguments
from app.services import inputs

Item = dict[str, Any] | Callable[[str, dict[str, Any]], dict[str, Any]]

DEFAULT_VISION_RESULT: dict[str, Any] = {
    "table_name": "legacy_customers",
    "fields": [
        {"name": "cust_id", "type": "varchar(20)", "nullable": False, "primary_key": True,
         "notes": "", "confidence": 0.95},
        {"name": "fullName", "type": "varchar(120)", "nullable": True, "primary_key": False,
         "notes": "", "confidence": 0.9},
        {"name": "email_addr", "type": "text", "nullable": True, "primary_key": False,
         "notes": "", "confidence": 0.9},
        {"name": "signup_dt", "type": "date", "nullable": True, "primary_key": False,
         "notes": "", "confidence": 0.5},
    ],
    "relationships": [],
}


def reference_plan() -> dict[str, Any]:
    return copy.deepcopy(inputs.reference_plan()["plan"])


def tool_call(name: str, arguments: dict[str, Any] | str | None = None) -> dict[str, Any]:
    return {"name": name, "arguments": {} if arguments is None else arguments}


def calls(*items: dict[str, Any]) -> dict[str, Any]:
    """One assistant turn with the given tool calls."""
    return {"tool_calls": list(items)}


class MockLLMClient:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._queues: dict[str, deque[Item]] = {}
        self._ids = itertools.count(1)
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def reset(self) -> None:
        with self._lock:
            self._queues.clear()
            self.calls.clear()

    def queue(self, alias: str, *items: Item) -> None:
        with self._lock:
            self._queues.setdefault(alias, deque()).extend(items)

    def calls_for(self, alias: str) -> list[dict[str, Any]]:
        return [req for a, req in self.calls if a == alias]

    def complete(self, engine: Engine, request: dict[str, Any], timeout_s: float) -> LLMResult:
        with self._lock:
            self.calls.append((engine.alias, copy.deepcopy(request)))
            queue = self._queues.get(engine.alias)
            item: Item = queue.popleft() if queue else _default_responder
        if callable(item):
            item = item(engine.alias, request)
        if "error" in item:
            raise ProviderError(item["error"], f"mock {item['error']}")
        return self._result(engine.alias, item, request)

    def _result(self, alias: str, item: dict[str, Any], request: dict[str, Any]) -> LLMResult:
        tool_calls: list[ToolCall] = []
        raw_calls: list[dict[str, Any]] = []
        for tc in item.get("tool_calls", []):
            call_id = f"call_{next(self._ids)}"
            args = tc.get("arguments", {})
            raw = args if isinstance(args, str) else json.dumps(args)
            tool_calls.append(ToolCall(call_id, tc["name"], parse_arguments(raw)))
            raw_calls.append({"id": call_id, "type": "function",
                              "function": {"name": tc["name"], "arguments": raw}})
        message: dict[str, Any] = {"role": "assistant", "content": item.get("content")}
        if raw_calls:
            message["tool_calls"] = raw_calls
            if alias == "backup":
                # Mirrors the backup engine: tool calls carry an opaque signature that must be
                # echoed back unchanged.
                for rc in raw_calls:
                    rc["extra_content"] = {"signature": f"sig-{rc['id']}"}
        message = {k: v for k, v in message.items() if v is not None}
        prompt_chars = len(json.dumps(request.get("messages", []), default=str))
        return LLMResult(
            engine=alias,
            content=item.get("content"),
            tool_calls=tool_calls,
            assistant_message=message,
            finish_reason="tool_calls" if tool_calls else "stop",
            tokens_in=prompt_chars // 4,
            tokens_out=40 + 10 * len(tool_calls),
            latency_ms=int(item.get("latency_ms", 5)),
        )


def _default_responder(_alias: str, request: dict[str, Any]) -> dict[str, Any]:
    if request.get("response_format", {}).get("type") == "json_object" and not request.get("tools"):
        return {"content": json.dumps(DEFAULT_VISION_RESULT)}
    tools = {t["function"]["name"] for t in request.get("tools", [])}
    has_tool_results = any(m.get("role") == "tool" for m in request.get("messages", []))
    if tools == {"submit_plan"} or has_tool_results:
        return calls(tool_call("submit_plan", reference_plan()))
    return calls(tool_call("get_source_schema"), tool_call("get_target_schema"),
                 tool_call("list_transformations"))


mock_client = MockLLMClient()
