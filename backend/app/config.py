"""Application settings.

Only three values are secrets (GROQ_API_KEY, GEMINI_API_KEY, DATABASE_URL). Everything else has a
default here and can be overridden through the environment.
"""

from __future__ import annotations

import hashlib
import hmac
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent
DATA_DIR = Path(__file__).resolve().parent / "data"

# Later files win, so a backend/.env overrides the repo-root .env. Real environment variables
# (HF Space secrets, CI) always win over both.
_ENV_FILES = tuple(str(p) for p in (REPO_ROOT / ".env", BACKEND_DIR / ".env") if p.is_file())


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILES or None,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- secrets (the only three keys in .env) ---
    groq_api_key: str = ""
    gemini_api_key: str = ""
    database_url: str = "sqlite:///./migrateiq-dev.db"

    # --- optional overrides ---
    database_url_direct: str = ""
    app_env: str = "development"
    llm_mode: str = "live"  # live | mock (mock is for tests only)
    # full | compact. Compact by default: the primary's free tier caps input tokens per minute
    # (measured 7,000), and a full-mode conversation resends every tool result on each turn.
    agent_mode: str = "compact"
    force_backup: bool = False

    primary_llm_base_url: str = "https://api.groq.com/openai/v1"
    primary_llm_model: str = "qwen/qwen3.8-27b"
    backup_llm_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    backup_llm_model: str = "gemini-3.8-flash"
    # Provider extras as JSON objects (sent through extra_body). The primary hides its reasoning
    # text so it can never leak into tool arguments or JSON output.
    primary_llm_extra_body: str = '{"reasoning_format": "hidden"}'
    backup_llm_extra_body: str = ""
    llm_timeout_s: float = 30.0
    backup_llm_timeout_s: float = 120.0
    llm_probe_timeout_s: float = 20.0
    llm_probe_ttl_s: int = 300
    llm_backup_probe_ttl_s: int = 21600  # the backup's free tier has a small daily quota
    llm_retry_delay_s: float = 1.0
    # On a 429 the gateway waits for the provider's Retry-After when it is at most this long
    # (the primary's free tier has a per-minute input-token cap); otherwise LLM_RETRY_DELAY_S.
    llm_rate_limit_max_wait_s: float = 30.0

    # --- agent (spec §7.1, §7.3) ---
    agent_max_steps: int = 12  # LLM turns in full mode
    agent_wall_s: float = 150.0  # full mode
    agent_compact_wall_s: float = 300.0
    agent_max_repairs: int = 2  # full mode; compact mode allows 1
    primary_max_completion_tokens: int = 8192
    backup_max_completion_tokens: int = 16384
    agent_runs_per_project_hour: int = 5
    agent_runs_global_hour: int = 40
    schema_imports_global_hour: int = 20
    agent_jobs_inline: bool = False  # tests only: run background jobs in the request thread

    jwt_secret: str = ""
    jwt_ttl_hours: int = 8
    demo_password: str = "migrateiq-demo"

    max_source_records: int = 500
    cors_origins: str = "http://localhost:5173"
    cors_origin_regex: str = ""
    fault_injection_enabled: bool = False
    log_level: str = "INFO"
    log_buffer_size: int = Field(default=1000, ge=10, le=10000)

    # ------------------------------------------------------------------ derived values
    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    @property
    def sqlalchemy_url(self) -> str:
        """Runtime URL (pooled endpoint on Neon) with the psycopg 3 driver."""
        return _with_psycopg_driver(self.database_url)

    @property
    def migration_url(self) -> str:
        """URL for Alembic: explicit direct URL, else the pooled URL with '-pooler' removed."""
        if self.database_url_direct:
            return _with_psycopg_driver(self.database_url_direct)
        return _with_psycopg_driver(_strip_pooler(self.database_url))

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def jwt_signing_key(self) -> str:
        if self.jwt_secret:
            return self.jwt_secret
        return hmac.new(
            self.database_url.encode("utf-8"), b"migrateiq-jwt-v1", hashlib.sha256
        ).hexdigest()

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def git_sha(self) -> str:
        sha_file = BACKEND_DIR / "GIT_SHA"
        if sha_file.is_file():
            value = sha_file.read_text(encoding="utf-8").strip()
            if value:
                return value
        return "dev"


def _with_psycopg_driver(url: str) -> str:
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix) :]
    return url


def _strip_pooler(url: str) -> str:
    if url.startswith("sqlite"):
        return url
    parts = urlsplit(url)
    netloc = parts.netloc.replace("-pooler.", ".")
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
