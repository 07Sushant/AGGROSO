"""Canonical JSON + SHA-256, used for plans, source snapshots, rows and dry-run results."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from datetime import date, datetime
from typing import Any


def _default(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=_default)


def sha256_hex(obj: Any) -> str:
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


def plan_hash(plan: dict[str, Any]) -> str:
    return sha256_hex(plan)


def payload_hash(payload: dict[str, Any]) -> str:
    return sha256_hex(payload)


def source_checksum(payload_hashes: Iterable[str]) -> str:
    """Checksum of a snapshot: the ordered list of per-row payload hashes."""
    return sha256_hex(list(payload_hashes))


def row_hash(row: dict[str, Any]) -> str:
    return sha256_hex(row)
