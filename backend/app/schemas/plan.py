"""The plan contract (spec §5.1), shared by the agent, the human editor and the engine.

Structural checks live here; semantic checks (fields exist, types chain, coverage) live in the
plan validator.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Severity = Literal["low", "medium", "high"]
Ident = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.\-]+$")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TransformStep(_Strict):
    name: str = Field(min_length=1, max_length=64)
    params: dict[str, Any] = Field(default_factory=dict)


class Risk(_Strict):
    id: str = Ident
    severity: Severity
    text: str = Field(min_length=1, max_length=1000)


class Mapping(_Strict):
    id: str = Ident
    target_field: str = Field(min_length=1, max_length=64)
    source_fields: list[str] = Field(default_factory=list, max_length=10)
    transforms: list[TransformStep] = Field(default_factory=list, max_length=12)
    on_error: Literal["quarantine", "set_null"] = "quarantine"
    confidence: Literal["high", "medium", "low"] = "medium"
    rationale: str = Field(default="", max_length=2000)
    risks: list[Risk] = Field(default_factory=list, max_length=10)


class PlanKey(_Strict):
    source_field: str = Field(min_length=1, max_length=64)
    target_field: str = Field(min_length=1, max_length=64)


class UnmappedSourceField(_Strict):
    field: str = Field(min_length=1, max_length=64)
    reason: str = Field(default="", max_length=1000)
    decision: str = Field(default="drop", max_length=64)


class UnmappedTargetField(_Strict):
    field: str = Field(min_length=1, max_length=64)
    reason: str = Field(default="", max_length=1000)
    proposed: TransformStep | None = None


class Incompatibility(_Strict):
    field: str = Field(min_length=1, max_length=64)
    issue: str = Field(min_length=1, max_length=1000)
    severity: Severity = "medium"


class ClarificationQuestion(_Strict):
    id: str = Ident
    question: str = Field(min_length=1, max_length=2000)
    related_fields: list[str] = Field(default_factory=list, max_length=20)
    options: list[str] = Field(default_factory=list, max_length=10)


class Plan(_Strict):
    key: PlanKey
    mappings: list[Mapping] = Field(min_length=1, max_length=50)
    unmapped_source_fields: list[UnmappedSourceField] = Field(default_factory=list)
    unmapped_target_fields: list[UnmappedTargetField] = Field(default_factory=list)
    incompatibilities: list[Incompatibility] = Field(default_factory=list)
    clarification_questions: list[ClarificationQuestion] = Field(
        default_factory=list, max_length=20
    )
    risk_summary: str = Field(default="", max_length=4000)

    def all_risks(self) -> list[Risk]:
        return [risk for m in self.mappings for risk in m.risks]


def normalize_plan(plan: Plan) -> dict[str, Any]:
    """The stored form of a plan: defaults made explicit, so the hash is stable."""
    return plan.model_dump(mode="json")
