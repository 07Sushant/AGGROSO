"""Dry runs: compute, store (bulk insert), query, export and determinism checks."""

from __future__ import annotations

import csv
import io
import json
import time
from collections import Counter
from typing import Any

from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.domain.dry_run import compute_dry_run
from app.domain.hashing import payload_hash, source_checksum
from app.errors import AppError
from app.models import DryRun, DryRunRecord, PlanVersion, SourceRecord
from app.security import CurrentUser
from app.services import audit, projects

EXPORT_COLUMNS = ("row_number", "source_key", "stage", "target_field", "source_fields",
                  "source_value", "transform", "rule", "code", "message")


def get_dry_run(db: Session, dry_run_id: int) -> DryRun:
    dry = db.get(DryRun, dry_run_id)
    if dry is None:
        raise AppError("NOT_FOUND", f"Dry run {dry_run_id} was not found.")
    return dry


def latest_for_version(db: Session, version_id: int) -> DryRun | None:
    return db.scalars(
        select(DryRun).where(DryRun.plan_version_id == version_id)
        .order_by(DryRun.id.desc()).limit(1)
    ).first()


def create_dry_run(db: Session, user: CurrentUser, version: PlanVersion) -> DryRun:
    started = time.perf_counter()
    rows = projects.source_rows(db, version.project_id)
    result = compute_dry_run(rows, version.plan)
    checksum = source_checksum(payload_hash(r.payload) for r in rows)
    dry = DryRun(
        plan_version_id=version.id,
        source_checksum=checksum,
        source_count=result.source_count,
        transformed_count=result.transformed_count,
        accepted_count=result.accepted_count,
        rejected_count=result.rejected_count,
        result_hash=result.result_hash,
        code_version=get_settings().git_sha,
        duration_ms=0,
        created_by=user.id,
    )
    db.add(dry)
    db.flush()
    if result.records:
        db.execute(insert(DryRunRecord), [
            {
                "dry_run_id": dry.id,
                "source_record_id": r.source_record_id,
                "row_number": r.row_number,
                "outcome": r.outcome,
                "transformed": r.transformed,
                "row_hash": r.row_hash,
                "errors": r.errors,
            }
            for r in result.records
        ])
    dry.duration_ms = int((time.perf_counter() - started) * 1000)
    audit.record(db, project_id=version.project_id, entity_type="dry_run", entity_id=dry.id,
                 action="dry_run.completed", actor_id=user.id,
                 details={"plan_version_id": version.id, "source": dry.source_count,
                          "transformed": dry.transformed_count, "accepted": dry.accepted_count,
                          "rejected": dry.rejected_count, "result_hash": dry.result_hash,
                          "rejected_by_code": result.rejected_by_code()})
    db.commit()
    return dry


def _records(db: Session, dry_run_id: int) -> list[tuple[DryRunRecord, SourceRecord]]:
    return list(db.execute(
        select(DryRunRecord, SourceRecord)
        .join(SourceRecord, SourceRecord.id == DryRunRecord.source_record_id)
        .where(DryRunRecord.dry_run_id == dry_run_id)
        .order_by(DryRunRecord.row_number)
    ).tuples().all())


def dry_run_out(db: Session, dry: DryRun) -> dict[str, Any]:
    codes: Counter[str] = Counter()
    fields: Counter[str] = Counter()
    for rec in db.scalars(select(DryRunRecord).where(DryRunRecord.dry_run_id == dry.id,
                                                     DryRunRecord.outcome == "REJECTED")).all():
        if rec.errors:
            codes[rec.errors[0]["code"]] += 1
            fields[rec.errors[0].get("target_field") or "-"] += 1
    return {
        "id": dry.id,
        "plan_version_id": dry.plan_version_id,
        "source_checksum": dry.source_checksum,
        "counts": {
            "source": dry.source_count,
            "transformed": dry.transformed_count,
            "accepted": dry.accepted_count,
            "rejected": dry.rejected_count,
        },
        "rejected_by_code": dict(sorted(codes.items())),
        "rejected_by_field": dict(sorted(fields.items())),
        "result_hash": dry.result_hash,
        "code_version": dry.code_version,
        "duration_ms": dry.duration_ms,
        "created_by": dry.created_by,
        "created_at": dry.created_at,
    }


def records_page(
    db: Session,
    dry_run_id: int,
    *,
    outcome: str | None,
    code: str | None,
    target_field: str | None,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    items = []
    for rec, src in _records(db, dry_run_id):
        if outcome and rec.outcome != outcome:
            continue
        if code and not any(e["code"] == code for e in rec.errors):
            continue
        if target_field and not any(e.get("target_field") == target_field for e in rec.errors):
            continue
        items.append({
            "row_number": rec.row_number,
            "source_record_id": rec.source_record_id,
            "source_key": src.source_key,
            "outcome": rec.outcome,
            "source": src.payload,
            "transformed": rec.transformed,
            "row_hash": rec.row_hash,
            "errors": rec.errors,
        })
    return {"total": len(items), "items": items[offset:offset + limit]}


def quarantine_evidence(db: Session, dry_run_id: int) -> list[dict[str, Any]]:
    out = []
    for rec, src in _records(db, dry_run_id):
        if rec.outcome != "REJECTED":
            continue
        for err in rec.errors:
            out.append({"row_number": rec.row_number, "source_key": src.source_key,
                        **{k: err.get(k) for k in EXPORT_COLUMNS[2:]}})
    return out


def export(db: Session, dry_run_id: int, fmt: str) -> tuple[str, str]:
    """Returns (content, media type)."""
    rows = quarantine_evidence(db, dry_run_id)
    if fmt == "json":
        return json.dumps(rows, indent=2, default=str), "application/json"
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(EXPORT_COLUMNS), lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({
            **row,
            "source_fields": "|".join(row["source_fields"] or []),
            "source_value": (json.dumps(row["source_value"])
                             if isinstance(row["source_value"], list) else row["source_value"]),
        })
    return buf.getvalue(), "text/csv"


def determinism_check(db: Session, version: PlanVersion, runs: int = 3) -> dict[str, Any]:
    """Recompute the dry run in memory several times; nothing is stored."""
    rows = projects.source_rows(db, version.project_id)
    hashes = [compute_dry_run(rows, version.plan).result_hash for _ in range(runs)]
    latest = latest_for_version(db, version.id)
    return {
        "plan_version_id": version.id,
        "runs": runs,
        "hashes": hashes,
        "deterministic": len(set(hashes)) == 1,
        "latest_dry_run_id": latest.id if latest else None,
        "matches_latest_dry_run": (latest.result_hash == hashes[0]) if latest else None,
    }
