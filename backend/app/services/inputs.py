"""Provided inputs (schemas, datasets, reference plan), loaded once and cached in memory."""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from app.config import DATA_DIR
from app.errors import AppError

DATASET_KEYS = ("baseline_60", "clean_25", "stress_500", "overflow_501")


def _load(name: str) -> Any:
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def source_schema() -> dict[str, Any]:
    return _load("source_schema.json")


@lru_cache(maxsize=1)
def target_schema() -> dict[str, Any]:
    return _load("target_schema.json")


@lru_cache(maxsize=1)
def reference_plan() -> dict[str, Any]:
    return _load("mock_plan.json")


@lru_cache(maxsize=1)
def gold_mapping() -> dict[str, Any]:
    return _load("gold_mapping.json")


@lru_cache(maxsize=len(DATASET_KEYS))
def dataset(key: str) -> dict[str, Any]:
    if key not in DATASET_KEYS:
        raise AppError("NOT_FOUND", f"Unknown dataset '{key}'.", details={"dataset_key": key})
    return _load(f"datasets/{key}.json")


def dataset_summaries(max_records: int) -> list[dict[str, Any]]:
    out = []
    for key in DATASET_KEYS:
        ds = dataset(key)
        out.append(
            {
                "key": ds["key"],
                "name": ds["name"],
                "description": ds["description"],
                "record_count": ds["record_count"],
                "within_limit": ds["record_count"] <= max_records,
            }
        )
    return out
