"""Read-only reconciliation (spec §6.6). It never creates dry runs and never writes data.

Totals, key sets (missing / unexpected in target), a per-row value check (target row hash
recomputed from stored column values vs the approved dry run's ``row_hash``) and invariants.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.hashing import row_hash
from app.domain.validation import target_columns
from app.models import Approval, DryRun, DryRunRecord, MigrationRun, RunRecordResult, TgtCustomer

MAX_MISMATCHES = 20


def _target_values(t: TgtCustomer) -> dict[str, Any]:
    out = {}
    for col in target_columns():
        value = getattr(t, col)
        out[col] = value.isoformat() if isinstance(value, date) else value
    return out


def reconcile(db: Session, run: MigrationRun) -> dict[str, Any]:
    approval = db.get(Approval, run.approval_id)
    dry = db.get(DryRun, approval.dry_run_id) if approval and approval.dry_run_id else None
    rolled_back = run.status == "ROLLED_BACK"

    counts = dict(db.execute(
        select(RunRecordResult.outcome, func.count())
        .where(RunRecordResult.run_id == run.id).group_by(RunRecordResult.outcome)
    ).tuples().all())
    inserted = counts.get("INSERTED", 0)
    skipped = counts.get("SKIPPED_EXISTING", 0)
    quarantined_exec = counts.get("QUARANTINED", 0)

    expected: dict[str, tuple[str, dict[str, Any]]] = {}
    if dry is not None and not rolled_back:
        for transformed, rhash in db.execute(
            select(DryRunRecord.transformed, DryRunRecord.row_hash)
            .join(RunRecordResult, (RunRecordResult.source_record_id
                                    == DryRunRecord.source_record_id))
            .where(RunRecordResult.run_id == run.id, RunRecordResult.outcome == "INSERTED",
                   DryRunRecord.dry_run_id == dry.id)
        ).tuples().all():
            expected[transformed["legacy_id"]] = (rhash, transformed)

    targets = db.scalars(
        select(TgtCustomer).where(TgtCustomer.project_id == run.project_id,
                                  TgtCustomer.migration_run_id == run.id)
    ).all()
    actual = {t.legacy_id: t for t in targets}
    missing = sorted(set(expected) - set(actual))
    unexpected = sorted(set(actual) - set(expected))

    mismatches: list[dict[str, Any]] = []
    mismatched_rows = 0
    for key in sorted(set(expected) & set(actual)):
        exp_hash, exp_values = expected[key]
        t = actual[key]
        values = _target_values(t)
        if row_hash(values) == exp_hash and t.row_hash == exp_hash:
            continue
        mismatched_rows += 1
        for col in target_columns():
            if values.get(col) != exp_values.get(col) and len(mismatches) < MAX_MISMATCHES:
                mismatches.append({"legacy_id": key, "field": col,
                                   "expected": exp_values.get(col), "actual": values.get(col)})

    source = dry.source_count if dry else 0
    transformed = dry.transformed_count if dry else 0
    accepted = dry.accepted_count if dry else 0
    rejected = dry.rejected_count if dry else 0
    target_rows = len(targets)

    invariants = [
        {"id": "source_equals_accepted_plus_rejected",
         "label": "source = accepted + rejected",
         "ok": source == accepted + rejected,
         "expected": source, "actual": accepted + rejected},
        {"id": "accepted_le_transformed_le_source",
         "label": "accepted <= transformed <= source",
         "ok": accepted <= transformed <= source,
         "expected": None, "actual": [accepted, transformed, source]},
    ]
    if not rolled_back:
        invariants.append(
            {"id": "execute_accounts_for_accepted",
             "label": "inserted + skipped + execute-quarantined = accepted",
             "ok": inserted + skipped + quarantined_exec == accepted,
             "expected": accepted, "actual": inserted + skipped + quarantined_exec})
    invariants.append(
        {"id": "target_rows_equal_inserted",
         "label": "target rows for the run = 0 after rollback" if rolled_back
                  else "target rows for the run = inserted",
         "ok": target_rows == (0 if rolled_back else inserted),
         "expected": 0 if rolled_back else inserted, "actual": target_rows})

    discrepancies: list[dict[str, Any]] = []
    for inv in invariants:
        if not inv["ok"]:
            discrepancies.append({"code": "INVARIANT_FAILED", "invariant": inv["id"],
                                  "message": f"{inv['label']} does not hold"})
    if missing:
        discrepancies.append({"code": "MISSING_IN_TARGET", "count": len(missing),
                              "message": f"{len(missing)} inserted records are not in the target"})
    if unexpected:
        discrepancies.append({"code": "UNEXPECTED_IN_TARGET", "count": len(unexpected),
                              "message": f"{len(unexpected)} target rows were not expected"})
    if mismatched_rows:
        discrepancies.append({"code": "VALUE_MISMATCH", "count": mismatched_rows,
                              "message": f"{mismatched_rows} target rows differ from the dry run"})

    return {
        "run_id": run.id,
        "run_status": run.status,
        "status": "FAIL" if discrepancies else "PASS",
        "totals": {
            "source": source, "transformed": transformed, "accepted": accepted,
            "rejected": rejected, "quarantined_dry_run": rejected,
            "quarantined_execute": quarantined_exec,
            "quarantined_total": rejected + quarantined_exec,
            "inserted": inserted, "skipped_existing": skipped, "target_rows": target_rows,
        },
        "missing_in_target": missing,
        "unexpected_in_target": unexpected,
        "value_mismatches": mismatches,
        "value_mismatch_rows": mismatched_rows,
        "invariants": invariants,
        "discrepancies": discrepancies,
    }
