"""Deterministic dry run (spec §6.1): a pure function of (snapshot rows, plan, code version).

It never reads or writes the target. Per record: apply each mapping's transform chain
(failures are transform errors), validate against the target schema, then check source
duplicates (first valid row wins).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.domain.hashing import row_hash, sha256_hex
from app.domain.transforms import TransformError, apply_transform, parse_params
from app.domain.validation import (
    DuplicateTracker,
    evidence,
    target_columns,
    unique_columns,
    validate_record,
)
from app.schemas.plan import Mapping, Plan
from app.services import inputs


@dataclass(frozen=True)
class SourceRow:
    id: int
    row_number: int
    payload: dict[str, Any]


@dataclass
class RecordResult:
    source_record_id: int
    row_number: int
    outcome: str  # ACCEPTED | REJECTED
    transformed: dict[str, Any] | None
    row_hash: str | None
    errors: list[dict[str, Any]]
    transform_failed: bool = False


@dataclass
class DryRunComputation:
    records: list[RecordResult] = field(default_factory=list)

    @property
    def source_count(self) -> int:
        return len(self.records)

    @property
    def transformed_count(self) -> int:
        return sum(1 for r in self.records if not r.transform_failed)

    @property
    def accepted_count(self) -> int:
        return sum(1 for r in self.records if r.outcome == "ACCEPTED")

    @property
    def rejected_count(self) -> int:
        return sum(1 for r in self.records if r.outcome == "REJECTED")

    @property
    def result_hash(self) -> str:
        return sha256_hex([
            [r.row_number, r.outcome, r.row_hash, sorted(e["code"] for e in r.errors)]
            for r in self.records
        ])

    def rejected_by_code(self) -> dict[str, int]:
        counts: Counter[str] = Counter()
        for r in self.records:
            if r.outcome == "REJECTED" and r.errors:
                counts[r.errors[0]["code"]] += 1
        return dict(sorted(counts.items()))


def to_jsonable(values: dict[str, Any]) -> dict[str, Any]:
    return {k: (v.isoformat() if isinstance(v, date) else v) for k, v in values.items()}


class CompiledPlan:
    def __init__(self, plan: Plan | dict[str, Any]) -> None:
        self.plan = plan if isinstance(plan, Plan) else Plan.model_validate(plan)
        self.mappings: list[tuple[Mapping, list[tuple[str, Any]]]] = [
            (m, [(s.name, parse_params(s.name, s.params)) for s in m.transforms])
            for m in self.plan.mappings
        ]

    def transform(
        self, payload: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, tuple[list[str], Any]], list[dict[str, Any]]]:
        """Apply every mapping. Returns (values, per-target source evidence, transform errors)."""
        values: dict[str, Any] = {name: None for name in target_columns()}
        sources: dict[str, tuple[list[str], Any]] = {}
        errors: list[dict[str, Any]] = []
        for mapping, steps in self.mappings:
            fields = mapping.source_fields
            if not fields:
                raw: Any = None
            elif len(fields) == 1:
                raw = payload.get(fields[0])
            else:
                raw = [payload.get(f) for f in fields]
            sources[mapping.target_field] = (list(fields), raw)
            value = raw
            for name, params in steps:
                try:
                    value = apply_transform(name, value, params)
                except TransformError as exc:
                    if mapping.on_error == "set_null":
                        value = None
                    else:
                        errors.append(evidence(
                            target_field=mapping.target_field, source_fields=fields,
                            source_value=raw, transform=name, rule="transform",
                            code=exc.code, message=exc.message, stage="transform",
                        ))
                    break
            values[mapping.target_field] = value
        return values, sources, errors


def compute_dry_run(rows: list[SourceRow], plan: Plan | dict[str, Any]) -> DryRunComputation:
    compiled = CompiledPlan(plan)
    key_field = inputs.target_schema()["key"]
    dupes = DuplicateTracker(key_field, unique_columns())
    out = DryRunComputation()
    for row in sorted(rows, key=lambda r: r.row_number):
        values, sources, t_errors = compiled.transform(row.payload)
        if t_errors:
            out.records.append(RecordResult(
                row.id, row.row_number, "REJECTED", to_jsonable(values), None, t_errors,
                transform_failed=True,
            ))
            continue
        errors = validate_record(values, sources) or dupes.check(row.row_number, values, sources)
        jsonable = to_jsonable(values)
        if errors:
            out.records.append(
                RecordResult(row.id, row.row_number, "REJECTED", jsonable, None, errors)
            )
        else:
            out.records.append(
                RecordResult(row.id, row.row_number, "ACCEPTED", jsonable, row_hash(jsonable), [])
            )
    return out
