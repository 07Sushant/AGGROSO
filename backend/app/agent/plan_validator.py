"""Deterministic plan validator (spec §6.2). Authoritative for agent output and human edits.

Errors are ``{code, path, message}`` so a model can repair against them. Nothing is auto-fixed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from app.domain.transforms import REGISTRY, TransformTypeError, parse_params, resolve_output_type
from app.schemas.plan import Plan, normalize_plan
from app.services import inputs


@dataclass
class PlanValidation:
    errors: list[dict[str, str]] = field(default_factory=list)
    warnings: list[dict[str, str]] = field(default_factory=list)
    plan: Plan | None = None

    @property
    def valid(self) -> bool:
        return not self.errors and self.plan is not None

    def add(self, code: str, path: str, message: str) -> None:
        self.errors.append({"code": code, "path": path, "message": message})

    def warn(self, code: str, path: str, message: str) -> None:
        self.warnings.append({"code": code, "path": path, "message": message})

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "errors": self.errors,
            "warnings": self.warnings,
            "plan": normalize_plan(self.plan) if self.valid and self.plan else None,
        }


def _input_type(source_fields: list[str], source_types: dict[str, str]) -> str:
    if not source_fields:
        return "none"
    if len(source_fields) == 1:
        return source_types.get(source_fields[0], "any")
    return "string[]"


def validate_plan(raw: Any) -> PlanValidation:
    result = PlanValidation()
    try:
        plan = Plan.model_validate(raw)
    except ValidationError as exc:
        for err in exc.errors():
            result.add(
                "SCHEMA_INVALID",
                ".".join(str(p) for p in err.get("loc", ())) or "$",
                err.get("msg", "Invalid value"),
            )
        return result
    result.plan = plan

    source = inputs.source_schema()
    target = inputs.target_schema()
    source_types = {f["name"]: f["type"] for f in source["fields"]}
    columns = {c["name"]: c for c in target["columns"]}

    # Key
    if plan.key.source_field not in source_types:
        result.add("UNKNOWN_SOURCE_FIELD", "key.source_field",
                   f"'{plan.key.source_field}' is not a source field")
    if plan.key.target_field != target["key"]:
        result.add("INVALID_KEY", "key.target_field",
                   f"the key must map to '{target['key']}', not '{plan.key.target_field}'")

    seen_mapping_ids: set[str] = set()
    seen_targets: dict[str, int] = {}
    seen_risk_ids: set[str] = set()
    mapped_sources: set[str] = set()

    for i, m in enumerate(plan.mappings):
        path = f"mappings[{i}]"
        if m.id in seen_mapping_ids:
            result.add("DUPLICATE_ID", f"{path}.id", f"mapping id '{m.id}' is used twice")
        seen_mapping_ids.add(m.id)

        for j, risk in enumerate(m.risks):
            if risk.id in seen_risk_ids:
                result.add("DUPLICATE_ID", f"{path}.risks[{j}].id",
                           f"risk id '{risk.id}' is used twice")
            seen_risk_ids.add(risk.id)

        column = columns.get(m.target_field)
        if column is None:
            result.add("UNKNOWN_TARGET_FIELD", f"{path}.target_field",
                       f"'{m.target_field}' is not a target column")
        elif m.target_field in seen_targets:
            first = seen_targets[m.target_field]
            result.add("DUPLICATE_TARGET_MAPPING", f"{path}.target_field",
                       f"'{m.target_field}' is already mapped by mappings[{first}]")
        else:
            seen_targets[m.target_field] = i

        bad_source = False
        for k, src in enumerate(m.source_fields):
            if src not in source_types:
                bad_source = True
                result.add("UNKNOWN_SOURCE_FIELD", f"{path}.source_fields[{k}]",
                           f"'{src}' is not a source field")
            mapped_sources.add(src)
        if len(set(m.source_fields)) != len(m.source_fields):
            result.add("DUPLICATE_SOURCE_FIELD", f"{path}.source_fields",
                       "a source field is listed twice")

        if m.on_error == "set_null" and column is not None and not column.get("nullable", False):
            result.add("SET_NULL_NOT_ALLOWED", f"{path}.on_error",
                       f"'{m.target_field}' is not nullable, so on_error must be 'quarantine'")

        # Transform existence, params and the type chain.
        current = _input_type(m.source_fields, source_types)
        chain_ok = not bad_source
        for k, step in enumerate(m.transforms):
            tpath = f"{path}.transforms[{k}]"
            if step.name not in REGISTRY:
                result.add("UNKNOWN_TRANSFORM", f"{tpath}.name",
                           f"'{step.name}' is not a registered transform")
                chain_ok = False
                continue
            try:
                params = parse_params(step.name, step.params)
            except ValidationError as exc:
                for err in exc.errors():
                    loc = ".".join(str(p) for p in err.get("loc", ()))
                    result.add("INVALID_TRANSFORM_PARAMS",
                               f"{tpath}.params" + (f".{loc}" if loc else ""),
                               err.get("msg", "Invalid value"))
                chain_ok = False
                continue
            if chain_ok:
                try:
                    current = resolve_output_type(step.name, params, current)
                except TransformTypeError as exc:
                    result.add("TYPE_MISMATCH", tpath, str(exc))
                    chain_ok = False
        if chain_ok and column is not None and current != column["type"]:
            result.add("TYPE_MISMATCH", f"{path}.transforms",
                       f"the chain produces {current} but '{m.target_field}' is {column['type']}")

    for name, column in columns.items():
        if column.get("required") and name not in seen_targets:
            result.add("REQUIRED_TARGET_UNMAPPED", "mappings",
                       f"required target column '{name}' has no mapping")

    key_mapping = next((m for m in plan.mappings if m.target_field == plan.key.target_field), None)
    if key_mapping is not None and plan.key.source_field not in key_mapping.source_fields:
        result.add("INVALID_KEY", "key.source_field",
                   f"the '{plan.key.target_field}' mapping does not read '{plan.key.source_field}'")

    seen_questions: set[str] = set()
    for i, q in enumerate(plan.clarification_questions):
        if q.id in seen_questions:
            result.add("DUPLICATE_ID", f"clarification_questions[{i}].id",
                       f"question id '{q.id}' is used twice")
        seen_questions.add(q.id)

    for i, u in enumerate(plan.unmapped_source_fields):
        if u.field not in source_types:
            result.add("UNKNOWN_SOURCE_FIELD", f"unmapped_source_fields[{i}].field",
                       f"'{u.field}' is not a source field")
    for i, u in enumerate(plan.unmapped_target_fields):
        if u.field not in columns:
            result.add("UNKNOWN_TARGET_FIELD", f"unmapped_target_fields[{i}].field",
                       f"'{u.field}' is not a target column")

    declared = {u.field for u in plan.unmapped_source_fields}
    for name in source_types:
        if name not in mapped_sources and name not in declared:
            result.warn("SOURCE_FIELD_UNACCOUNTED", "unmapped_source_fields",
                        f"source field '{name}' is neither mapped nor listed as unmapped")
    return result
