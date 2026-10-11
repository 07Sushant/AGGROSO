"""Target-record validation (spec §6.1 step 2) and source duplicate detection (step 3).

Every error is field-level evidence:
``{target_field, source_fields, source_value, transform, rule, code, message, stage}``.
"""

from __future__ import annotations

import re
from datetime import date
from functools import lru_cache
from typing import Any

from app.services import inputs


def evidence(
    *,
    target_field: str | None,
    source_fields: list[str],
    source_value: Any,
    rule: str,
    code: str,
    message: str,
    stage: str,
    transform: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    item = {
        "target_field": target_field,
        "source_fields": list(source_fields),
        "source_value": source_value,
        "transform": transform,
        "rule": rule,
        "code": code,
        "message": message,
        "stage": stage,
    }
    item.update(extra)
    return item


@lru_cache(maxsize=1)
def _compiled_columns() -> tuple[dict[str, Any], ...]:
    out = []
    for col in inputs.target_schema()["columns"]:
        c = dict(col)
        if col.get("regex"):
            c["_regex"] = re.compile(col["regex"])
        out.append(c)
    return tuple(out)


def target_columns() -> list[str]:
    return [c["name"] for c in _compiled_columns()]


def _type_ok(value: Any, expected: str) -> bool:
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "date":
        return isinstance(value, date)
    return False


def _is_empty(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def validate_record(
    values: dict[str, Any],
    sources: dict[str, tuple[list[str], Any]],
) -> list[dict[str, Any]]:
    """Check transformed values against the target schema.

    ``sources`` maps a target field to ``(source_fields, raw source value)`` for the evidence.
    Rules per column, in order: required, type, max length, regex, enum, range. The first failing
    rule for a column is reported.
    """
    errors: list[dict[str, Any]] = []
    for col in _compiled_columns():
        failure = _check_column(col, values.get(col["name"]))
        if failure is not None:
            rule, code, message = failure
            src_fields, src_value = sources.get(col["name"], ([], None))
            errors.append(evidence(
                target_field=col["name"], source_fields=src_fields, source_value=src_value,
                rule=rule, code=code, message=message, stage="validate",
            ))
    return errors


def _check_column(col: dict[str, Any], value: Any) -> tuple[str, str, str] | None:
    name = col["name"]
    if _is_empty(value):
        if not col.get("nullable", False):
            return ("required", "REQUIRED_FIELD_EMPTY", f"{name} is required")
        return None
    if not _type_ok(value, col["type"]):
        return ("type", "TYPE_MISMATCH", f"{name} must be {col['type']}")
    if col.get("max_length") and isinstance(value, str) and len(value) > col["max_length"]:
        return ("max_length", "MAX_LENGTH", f"{name} is longer than {col['max_length']}")
    if "_regex" in col and not col["_regex"].match(value):
        return ("regex", "REGEX_MISMATCH", f"{name} '{value}' does not match the required format")
    if col.get("enum") and value not in col["enum"]:
        return ("enum", "ENUM_MISMATCH", f"{name} '{value}' is not one of {col['enum']}")
    if "min" in col and value < col["min"]:
        return ("range", "RANGE", f"{name} {value} is below the minimum {col['min']}")
    return None


class DuplicateTracker:
    """First row wins. Keys are claimed only by rows that are otherwise valid."""

    def __init__(self, key_field: str, unique_fields: list[str]) -> None:
        self.key_field = key_field
        self.unique_fields = [f for f in unique_fields if f != key_field]
        self._keys: dict[Any, int] = {}
        self._uniques: dict[str, dict[Any, int]] = {f: {} for f in self.unique_fields}

    @staticmethod
    def _norm(value: Any) -> Any:
        return value.strip().casefold() if isinstance(value, str) else value

    def check(
        self, row_number: int, values: dict[str, Any], sources: dict[str, tuple[list[str], Any]]
    ) -> list[dict[str, Any]]:
        key = self._norm(values.get(self.key_field))
        if key in self._keys:
            src_fields, src_value = sources.get(self.key_field, ([], None))
            return [evidence(
                target_field=self.key_field, source_fields=src_fields, source_value=src_value,
                rule="unique", code="DUPLICATE_SOURCE_KEY", stage="validate",
                message=f"{self.key_field} '{values.get(self.key_field)}' already used by "
                        f"row {self._keys[key]}",
                first_row_number=self._keys[key],
            )]
        for f in self.unique_fields:
            norm = self._norm(values.get(f))
            if norm is not None and norm in self._uniques[f]:
                src_fields, src_value = sources.get(f, ([], None))
                return [evidence(
                    target_field=f, source_fields=src_fields, source_value=src_value,
                    rule="unique", code="DUPLICATE_EMAIL" if f == "email" else "DUPLICATE_VALUE",
                    stage="validate",
                    message=f"{f} '{values.get(f)}' already used by row {self._uniques[f][norm]}",
                    first_row_number=self._uniques[f][norm],
                )]
        self._keys[key] = row_number
        for f in self.unique_fields:
            norm = self._norm(values.get(f))
            if norm is not None:
                self._uniques[f][norm] = row_number
        return []


def unique_columns() -> list[str]:
    return [c["name"] for c in _compiled_columns() if c.get("unique")]
