"""LLM engine definitions. Both engines speak the OpenAI-compatible API through one SDK.

Public vocabulary is the alias only (``primary`` / ``backup``); model ids and base URLs stay
internal and are never serialised to clients.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from openai import OpenAI

from app.config import Settings, get_settings


@dataclass(frozen=True)
class Engine:
    alias: str  # "primary" | "backup"
    base_url: str
    api_key: str
    model: str
    timeout_s: float
    # Provider-specific request fields (for example reasoning flags), sent through extra_body.
    extra_body: dict[str, Any] = field(default_factory=dict)

    @property
    def configured(self) -> bool:
        return bool(self.api_key)


def _extra(raw: str) -> dict[str, Any]:
    if not raw.strip():
        return {}
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("LLM extra body settings must be JSON objects")
    return value


def engines(settings: Settings | None = None) -> list[Engine]:
    settings = settings or get_settings()
    return [
        Engine(
            "primary",
            settings.primary_llm_base_url,
            settings.groq_api_key,
            settings.primary_llm_model,
            settings.llm_timeout_s,
            _extra(settings.primary_llm_extra_body),
        ),
        Engine(
            "backup",
            settings.backup_llm_base_url,
            settings.gemini_api_key,
            settings.backup_llm_model,
            settings.backup_llm_timeout_s,
            _extra(settings.backup_llm_extra_body),
        ),
    ]


def request_options(engine: Engine, *, max_completion_tokens: int) -> dict[str, Any]:
    """Options every chat call carries. Output is always bounded: unbounded reasoning output
    made calls run into the client timeout."""
    options: dict[str, Any] = {"max_completion_tokens": max_completion_tokens}
    if engine.extra_body:
        options["extra_body"] = dict(engine.extra_body)
    return options


def make_client(engine: Engine, timeout_s: float | None = None) -> OpenAI:
    # Retries are handled by the gateway's failover policy, not by the SDK.
    return OpenAI(
        api_key=engine.api_key,
        base_url=engine.base_url,
        timeout=timeout_s or engine.timeout_s,
        max_retries=0,
    )
