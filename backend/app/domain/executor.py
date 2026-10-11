"""Chunked, transactional, idempotent execution into the mock target (spec §6.5).

- Each chunk's target inserts and ``run_record_results`` rows commit in one transaction.
- Fast path: ``INSERT ... ON CONFLICT DO NOTHING RETURNING legacy_id`` for the whole chunk. Rows
  that are not returned are classified (skipped existing key, or quarantined unique conflict).
- Slow path: if the chunk raises anything else (for example a CHECK violation), it is retried row
  by row inside SAVEPOINTs and the bad rows are quarantined with the database error.
- Only records without a result row are processed, so a retry never duplicates work.
- Before writing, every chunk's recomputed ``row_hash`` values must equal the approved dry run's.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import insert, or_, select
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.orm import Session

from app.db import insert_ignore
from app.domain.dry_run import SourceRow, compute_dry_run
from app.domain.validation import evidence, target_columns
from app.models import DryRunRecord, MigrationRun, RunAttempt, RunRecordResult, TgtCustomer

CHUNK_SIZE = 100
_TABLE = TgtCustomer.__table__


class FaultInjected(Exception):
    def __init__(self, processed: int) -> None:
        super().__init__(f"Injected fault after {processed} records")
        self.processed = processed


class DriftDetected(Exception):
    def __init__(self, row_numbers: list[int]) -> None:
        super().__init__(f"{len(row_numbers)} records no longer match the approved dry run")
        self.row_numbers = row_numbers


@dataclass(frozen=True)
class PendingRecord:
    source_record_id: int
    row_number: int
    transformed: dict[str, Any]
    row_hash: str


def target_row(project_id: int, run_id: int, rec: PendingRecord) -> dict[str, Any]:
    row: dict[str, Any] = {col: rec.transformed.get(col) for col in target_columns()}
    if isinstance(row.get("signup_date"), str):
        row["signup_date"] = date.fromisoformat(row["signup_date"])
    row.update(project_id=project_id, migration_run_id=run_id, row_hash=rec.row_hash)
    return row


def pending_records(db: Session, run: MigrationRun, dry_run_id: int) -> list[PendingRecord]:
    done = select(RunRecordResult.source_record_id).where(RunRecordResult.run_id == run.id)
    rows = db.execute(
        select(DryRunRecord.source_record_id, DryRunRecord.row_number,
               DryRunRecord.transformed, DryRunRecord.row_hash)
        .where(DryRunRecord.dry_run_id == dry_run_id, DryRunRecord.outcome == "ACCEPTED",
               DryRunRecord.source_record_id.not_in(done))
        .order_by(DryRunRecord.row_number)
    ).all()
    return [PendingRecord(r.source_record_id, r.row_number, r.transformed, r.row_hash)
            for r in rows]


def _db_error_message(exc: Exception) -> str:
    orig = getattr(exc, "orig", None)
    diag = getattr(orig, "diag", None)
    name = getattr(diag, "constraint_name", None) if diag is not None else None
    if name:
        return f"The target rejected the row (constraint {name})."
    text = str(orig if orig is not None else exc).splitlines()[0][:200]
    return f"The target rejected the row ({text})."


def _insert(db: Session, rows: list[dict[str, Any]]) -> set[str]:
    stmt = insert_ignore(_TABLE, db.get_bind().dialect.name).values(rows).returning(
        _TABLE.c.legacy_id)
    return set(db.execute(stmt).scalars().all())


def write_chunk(
    db: Session, run: MigrationRun, attempt: RunAttempt, chunk: list[PendingRecord]
) -> dict[str, int]:
    """Insert one chunk and record per-record outcomes. The caller commits."""
    rows = [target_row(run.project_id, run.id, rec) for rec in chunk]
    outcomes: dict[int, tuple[str, list[dict[str, Any]]]] = {}
    try:
        with db.begin_nested():
            inserted = _insert(db, rows)
    except (IntegrityError, DataError):
        inserted = set()
        for rec, row in zip(chunk, rows, strict=True):
            try:
                with db.begin_nested():
                    inserted |= _insert(db, [row])
            except (IntegrityError, DataError) as exc:
                outcomes[rec.source_record_id] = ("QUARANTINED", [evidence(
                    target_field=None, source_fields=[], source_value=None,
                    rule="target_constraint", code="TARGET_CONSTRAINT_VIOLATION",
                    message=_db_error_message(exc), stage="execute",
                )])

    for rec in chunk:
        if rec.transformed["legacy_id"] in inserted and rec.source_record_id not in outcomes:
            outcomes[rec.source_record_id] = ("INSERTED", [])

    leftover = [rec for rec in chunk if rec.source_record_id not in outcomes]
    if leftover:
        keys = [rec.transformed["legacy_id"] for rec in leftover]
        emails = [rec.transformed["email"] for rec in leftover]
        existing = db.execute(
            select(TgtCustomer.legacy_id, TgtCustomer.email, TgtCustomer.migration_run_id)
            .where(TgtCustomer.project_id == run.project_id,
                   or_(TgtCustomer.legacy_id.in_(keys), TgtCustomer.email.in_(emails)))
        ).all()
        by_key = {e.legacy_id: e for e in existing}
        by_email = {e.email: e for e in existing}
        for rec in leftover:
            key, email = rec.transformed["legacy_id"], rec.transformed["email"]
            if key in by_key:
                owner = by_key[key].migration_run_id
                if owner == run.id:
                    # Written by this run earlier: already counted, never relabelled.
                    outcomes[rec.source_record_id] = ("INSERTED", [])
                else:
                    outcomes[rec.source_record_id] = ("SKIPPED_EXISTING", [evidence(
                        target_field="legacy_id", source_fields=[], source_value=key,
                        rule="unique", code="TARGET_KEY_EXISTS", stage="execute",
                        message=f"legacy_id '{key}' already exists in the target",
                        existing_run_id=owner,
                    )])
            elif email in by_email:
                outcomes[rec.source_record_id] = ("QUARANTINED", [evidence(
                    target_field="email", source_fields=[], source_value=email,
                    rule="unique", code="TARGET_UNIQUE_CONFLICT", stage="execute",
                    message=f"email '{email}' already belongs to legacy_id "
                            f"'{by_email[email].legacy_id}' in the target",
                    existing_legacy_id=by_email[email].legacy_id,
                )])
            else:
                outcomes[rec.source_record_id] = ("QUARANTINED", [evidence(
                    target_field=None, source_fields=[], source_value=key,
                    rule="unique", code="TARGET_UNIQUE_CONFLICT", stage="execute",
                    message="the target rejected the row on a unique key",
                )])

    db.execute(insert(RunRecordResult), [
        {"run_id": run.id, "source_record_id": sid, "attempt_id": attempt.id,
         "outcome": outcome, "errors": errors}
        for sid, (outcome, errors) in outcomes.items()
    ])
    counts = {"INSERTED": 0, "SKIPPED_EXISTING": 0, "QUARANTINED": 0}
    for outcome, _ in outcomes.values():
        counts[outcome] += 1
    attempt.inserted += counts["INSERTED"]
    attempt.skipped_existing += counts["SKIPPED_EXISTING"]
    attempt.quarantined += counts["QUARANTINED"]
    return counts


def process_attempt(
    db: Session,
    run: MigrationRun,
    attempt: RunAttempt,
    *,
    plan: dict[str, Any],
    source_rows: list[SourceRow],
    dry_run_id: int,
    simulate_failure_after: int | None = None,
) -> int:
    """Process every pending record in chunks. Returns how many records were processed.

    Raises ``DriftDetected`` (nothing written for that chunk) or ``FaultInjected`` (after the
    first ``simulate_failure_after`` records were committed).
    """
    recomputed = {
        r.source_record_id: (r.outcome, r.row_hash)
        for r in compute_dry_run(source_rows, plan).records
    }
    pending = pending_records(db, run, dry_run_id)
    processed = 0
    for start in range(0, len(pending), CHUNK_SIZE):
        chunk = pending[start:start + CHUNK_SIZE]
        if simulate_failure_after is not None:
            chunk = chunk[: max(0, simulate_failure_after - processed)]
        drifted = [rec.row_number for rec in chunk
                   if recomputed.get(rec.source_record_id) != ("ACCEPTED", rec.row_hash)]
        if drifted:
            raise DriftDetected(drifted)
        if chunk:
            write_chunk(db, run, attempt, chunk)
            db.commit()
            processed += len(chunk)
        if simulate_failure_after is not None and processed >= simulate_failure_after:
            raise FaultInjected(processed)
    return processed
