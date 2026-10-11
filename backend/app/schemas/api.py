"""Request/response DTOs. Provider and model names never appear in any of these."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=200)


class UserOut(BaseModel):
    id: int
    username: str
    role: Literal["operator", "approver"]


class LoginResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    user: UserOut


class DbHealth(BaseModel):
    status: Literal["ok", "down"]
    latency_ms: int | None = None


class AiHealth(BaseModel):
    status: Literal["primary", "backup", "degraded", "down", "mock"]
    primary: str
    backup: str
    checked_at: str | None = None


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    env: str
    db: DbHealth
    ai: AiHealth


class LiveResponse(BaseModel):
    status: Literal["ok"] = "ok"


class ConfigResponse(BaseModel):
    app_env: str
    version: str
    max_source_records: int
    fault_injection_enabled: bool
    llm_mode: Literal["live", "mock"]
    demo_accounts: list[dict[str, str]]


class DatasetSummary(BaseModel):
    key: str
    name: str
    description: str
    record_count: int
    within_limit: bool


class TransformInfo(BaseModel):
    name: str
    description: str
    input_type: str
    output_type: str
    params_schema: dict[str, Any]


class LogsResponse(BaseModel):
    items: list[dict[str, Any]]
    count: int


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    dataset_key: str = Field(min_length=1, max_length=64)


class PlanVersionCreate(BaseModel):
    plan: dict[str, Any]
    change_note: str = Field(min_length=1, max_length=2000)
    parent_version_id: int | None = None


class PlanValidateRequest(BaseModel):
    plan: dict[str, Any] | None = None


class AnswersRequest(BaseModel):
    answers: dict[str, Annotated[str, Field(min_length=1, max_length=2000)]] = Field(
        min_length=1, max_length=50)


class RiskAckRequest(BaseModel):
    risk_ids: list[str] = Field(min_length=1, max_length=100)


class ApproveRequest(BaseModel):
    comment: str | None = Field(default=None, max_length=2000)


class CommentRequired(BaseModel):
    comment: str = Field(min_length=1, max_length=2000)


class ExecuteRequest(BaseModel):
    simulate_failure_after: int | None = Field(default=None, ge=1, le=10000)


class RollbackRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=2000)
