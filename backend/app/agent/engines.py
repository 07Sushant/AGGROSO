"""LLM engine definitions. Both engines speak the OpenAI-compatible API through one SDK.

Public vocabulary is the alias only (``primary`` / ``backup``); model ids and base URLs stay
internal and are never serialised to clients.
"""

from __future__ import annotations

from dataclasses import dataclass

from openai import OpenAI

from app.config import Settings, get_settings


@dataclass(frozen=True)
class Engine:
    alias: str  # "primary" | "backup"
    base_url: str
    api_key: str
    model: str
    timeout_s: float

    @property
    def configured(self) -> bool:
        return bool(self.api_key)


def engines(settings: Settings | None = None) -> list[Engine]:
    settings = settings or get_settings()
    return [
        Engine(
            "primary",
            settings.primary_llm_base_url,
            settings.groq_api_key,
            settings.primary_llm_model,
            settings.llm_timeout_s,
        ),
        Engine(
            "backup",
            settings.backup_llm_base_url,
            settings.gemini_api_key,
            settings.backup_llm_model,
            settings.backup_llm_timeout_s,
        ),
    ]


def make_client(engine: Engine, timeout_s: float | None = None) -> OpenAI:
    # Retries are handled by the gateway's failover policy, not by the SDK.
    return OpenAI(
        api_key=engine.api_key,
        base_url=engine.base_url,
        timeout=timeout_s or engine.timeout_s,
        max_retries=0,
    )
