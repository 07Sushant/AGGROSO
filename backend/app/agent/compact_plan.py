"""The compact plan the model writes through ``submit_plan``, and its deterministic expansion.

The primary engine's free tier allows about 1,000 output tokens per minute, so the model writes
only the decisions: per mapping the target, sources, transforms, confidence and a short
rationale; risks, questions and incompatibilities as short items with ids. Code then fills in
what follows mechanically from the schemas (mapping ids, ``on_error`` defaults, risks attached
to their mapping, unmapped source and target fields) and the full plan goes through the
deterministic validator. Nothing the model decided is changed.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.agent.plan_validator import PlanValidation, validate_plan
from app.schemas.plan import Ident, Severity, TransformStep
from app.services import inputs


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CompactMapping(_Strict):
    target_field: str = Field(min_length=1, max_length=64)
    # Required (an empty list only for constant targets): when optional, the primary engine
    # omitted it on every mapping (seen live) and every transform chain lost its input.
    source_fields: list[str] = Field(max_length=10, description=(
        "Source columns this target reads from; [] only for a constant with no source."))
    transforms: list[TransformStep] = Field(default_factory=list, max_length=12)
    confidence: Literal["high", "medium", "low"] = "medium"
    rationale: str = Field(default="", max_length=200, description="At most 12 words.")
    on_error: Literal["quarantine", "set_null"] = "quarantine"


class CompactRisk(_Strict):
    id: str = Ident
    target_field: str = Field(min_length=1, max_length=64,
                              description="The mapping this risk belongs to.")
    severity: Severity
    text: str = Field(min_length=1, max_length=300)


class CompactQuestion(_Strict):
    id: str = Ident
    question: str = Field(min_length=1, max_length=400)
    related_fields: list[str] = Field(default_factory=list, max_length=10)
    options: list[str] = Field(default_factory=list, max_length=5)


class CompactIncompatibility(_Strict):
    field: str = Field(min_length=1, max_length=64)
    issue: str = Field(min_length=1, max_length=300)
    severity: Severity = "medium"


class CompactKey(_Strict):
    source_field: str = Field(min_length=1, max_length=64)
    target_field: str = Field(min_length=1, max_length=64)


class CompactPlan(_Strict):
    key: CompactKey
    mappings: list[CompactMapping] = Field(min_length=1, max_length=50)
    risks: list[CompactRisk] = Field(default_factory=list, max_length=20)
    questions: list[CompactQuestion] = Field(default_factory=list, max_length=10)
    incompatibilities: list[CompactIncompatibility] = Field(default_factory=list, max_length=20)
    risk_summary: str = Field(default="", max_length=600)


def _with_key_mapping(compact: CompactPlan) -> CompactPlan:
    """The key mapping follows mechanically from the model's own ``key`` decision; models
    often state the key but skip repeating it as a mapping, so code adds it (trim only)."""
    if any(m.target_field == compact.key.target_field for m in compact.mappings):
        return compact
    key_mapping = CompactMapping(
        target_field=compact.key.target_field, source_fields=[compact.key.source_field],
        transforms=[TransformStep(name="trim")], confidence="high",
        rationale="Key column carried over (derived from the plan key).")
    return compact.model_copy(update={"mappings": [key_mapping, *compact.mappings]})


def expand(compact: CompactPlan) -> dict[str, Any]:
    """Compact plan -> full plan contract (spec §5.1)."""
    compact = _with_key_mapping(compact)
    source_names = [f["name"] for f in inputs.source_schema()["fields"]]
    columns = [c["name"] for c in inputs.target_schema()["columns"]]
    risks_by_target: dict[str, list[dict[str, Any]]] = {}
    for r in compact.risks:
        risks_by_target.setdefault(r.target_field, []).append(
            {"id": r.id, "severity": r.severity, "text": r.text})
    mappings = [
        {
            "id": f"m_{m.target_field}",
            "target_field": m.target_field,
            "source_fields": list(m.source_fields),
            "transforms": [t.model_dump() for t in m.transforms],
            "on_error": m.on_error,
            "confidence": m.confidence,
            "rationale": m.rationale,
            "risks": risks_by_target.pop(m.target_field, []),
        }
        for m in compact.mappings
    ]
    # A risk for a target the model did not map stays visible on the first mapping.
    orphans = [r for items in risks_by_target.values() for r in items]
    if orphans and mappings:
        mappings[0]["risks"].extend(orphans)
    mapped_sources = {s for m in compact.mappings for s in m.source_fields}
    mapped_targets = {m.target_field: m for m in compact.mappings}
    unmapped_targets: list[dict[str, Any]] = []
    for col in columns:
        m = mapped_targets.get(col)
        if m is None:
            unmapped_targets.append({"field": col, "reason": "no mapping", "proposed": None})
        elif not m.source_fields:
            unmapped_targets.append({
                "field": col, "reason": "no source column",
                "proposed": m.transforms[0].model_dump() if m.transforms else None})
    return {
        "key": compact.key.model_dump(),
        "mappings": mappings,
        "unmapped_source_fields": [
            {"field": s, "reason": "not used by any mapping", "decision": "drop"}
            for s in source_names if s not in mapped_sources
        ],
        "unmapped_target_fields": unmapped_targets,
        "incompatibilities": [i.model_dump() for i in compact.incompatibilities],
        "clarification_questions": [q.model_dump() for q in compact.questions],
        "risk_summary": compact.risk_summary,
    }


def _strip_foreign_params(raw: Any) -> list[dict[str, str]]:
    """The submit_plan tool shares one params object across all transforms, so models sometimes
    copy a key that belongs to another transform (seen live: ``value`` inside ``map_values``).
    Keys the named transform does not define are removed and reported as warnings; required
    params are never invented, so a missing one still fails validation."""
    from app.domain.transforms import REGISTRY

    warnings: list[dict[str, str]] = []
    if not isinstance(raw, dict):
        return warnings
    for i, m in enumerate(raw.get("mappings") or []):
        if not isinstance(m, dict):
            continue
        for j, t in enumerate(m.get("transforms") or []):
            if not isinstance(t, dict) or not isinstance(t.get("params"), dict):
                continue
            spec = REGISTRY.get(t.get("name", ""))
            if spec is None:
                continue
            allowed = set(spec.params_model.model_fields)
            for key in [k for k in t["params"] if k not in allowed]:
                del t["params"][key]
                warnings.append({"code": "PARAM_DROPPED",
                                 "path": f"mappings[{i}].transforms[{j}].params.{key}",
                                 "message": f"'{key}' is not a parameter of {spec.name}; removed"})
    return warnings


def validate_compact(raw: Any) -> PlanValidation:
    """Parse the compact plan, expand it, then run the authoritative plan validator."""
    dropped = _strip_foreign_params(raw)
    try:
        compact = CompactPlan.model_validate(raw)
    except ValidationError as exc:
        result = PlanValidation()
        for err in exc.errors():
            result.add("SCHEMA_INVALID", ".".join(str(p) for p in err.get("loc", ())) or "$",
                       err.get("msg", "Invalid value"))
        return result
    result = validate_plan(expand(compact))
    result.warnings[:0] = dropped
    return result


def to_compact(plan: dict[str, Any]) -> dict[str, Any]:
    """Full plan -> compact form (used by the mock LLM and the tests)."""
    return {
        "key": dict(plan["key"]),
        "mappings": [
            {"target_field": m["target_field"], "source_fields": list(m["source_fields"]),
             "transforms": [{"name": t["name"], "params": t.get("params", {})}
                            for t in m["transforms"]],
             "confidence": m.get("confidence", "medium"),
             "rationale": m.get("rationale", ""),
             **({"on_error": m["on_error"]} if m.get("on_error", "quarantine") != "quarantine"
                else {})}
            for m in plan["mappings"]
        ],
        "risks": [{"id": r["id"], "target_field": m["target_field"], "severity": r["severity"],
                   "text": r["text"]} for m in plan["mappings"] for r in m.get("risks", [])],
        "questions": [dict(q) for q in plan.get("clarification_questions", [])],
        "incompatibilities": [dict(i) for i in plan.get("incompatibilities", [])],
        "risk_summary": plan.get("risk_summary", ""),
    }
