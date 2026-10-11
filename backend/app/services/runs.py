"""Execute (idempotent, synchronous), retry, rollback, reconciliation, history, stale recovery."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.domain import executor
from app.domain.hashing import plan_hash
from app.domain.reconciliation import reconcile
from app.domain.state import transition
from app.domain.validation import target_columns
from app.errors import AppError
from app.logging import get_logger
from app.models import (
    AgentRun,
    Approval,
    AuditEvent,
    DryRun,
    DryRunRecord,
    MigrationRun,
    PlanVersion,
    Rollback,
    RunAttempt,
    RunRecordResult,
    SourceRecord,
    TgtCustomer,
    User,
    utcnow,
)
from app.security import CurrentUser
from app.services import audit, plans, projects

log = get_logger("app")
STALE_AFTER = timedelta(minutes=10)


def fingerprint(version_id: int, user_id: int) -> str:
    return hashlib.sha256(f"{version_id}:{user_id}".encode()).hexdigest()


def get_run(db: Session, run_id: int) -> MigrationRun:
    run = db.get(MigrationRun, run_id)
    if run is None:
        raise AppError("NOT_FOUND", f"Run {run_id} was not found.")
    return run


def _attempts(db: Session, run_id: int) -> list[RunAttempt]:
    return list(db.scalars(select(RunAttempt).where(RunAttempt.run_id == run_id)
                           .order_by(RunAttempt.attempt_number)).all())


def attempt_out(a: RunAttempt) -> dict[str, Any]:
    return {
        "id": a.id, "attempt_number": a.attempt_number, "kind": a.kind, "status": a.status,
        "inserted": a.inserted, "skipped_existing": a.skipped_existing,
        "quarantined": a.quarantined, "error_code": a.error_code,
        "error_message": a.error_message, "started_at": a.started_at,
        "finished_at": a.finished_at,
    }


def run_out(db: Session, run: MigrationRun, **extra: Any) -> dict[str, Any]:
    attempts = _attempts(db, run.id)
    last_failed = next((a for a in reversed(attempts) if a.status == "FAILED"), None)
    out = {
        "id": run.id, "project_id": run.project_id, "plan_version_id": run.plan_version_id,
        "approval_id": run.approval_id, "idempotency_key": run.idempotency_key,
        "status": run.status, "inserted": run.inserted,
        "skipped_existing": run.skipped_existing, "quarantined": run.quarantined,
        "created_by": run.created_by, "created_at": run.created_at,
        "updated_at": run.updated_at, "finished_at": run.finished_at,
        "attempts": [attempt_out(a) for a in attempts],
        "last_error": (
            {"code": last_failed.error_code, "message": last_failed.error_message}
            if last_failed and run.status == "FAILED" else None
        ),
        "replayed": False,
    }
    out.update(extra)
    return out


def recompute_totals(db: Session, run: MigrationRun) -> None:
    counts = dict(db.execute(
        select(RunRecordResult.outcome, func.count())
        .where(RunRecordResult.run_id == run.id).group_by(RunRecordResult.outcome)
    ).tuples().all())
    run.inserted = counts.get("INSERTED", 0)
    run.skipped_existing = counts.get("SKIPPED_EXISTING", 0)
    run.quarantined = counts.get("QUARANTINED", 0)


def _verified_approval(db: Session, version: PlanVersion, approval_id: int | None = None
                       ) -> tuple[Approval, DryRun]:
    """The approval gate for execute and retry (spec §6.4)."""
    if version.status != "APPROVED":
        raise AppError("APPROVAL_REQUIRED",
                       f"Version {version.version_number} is {version.status}, not APPROVED.",
                       details={"status": version.status})
    if approval_id is not None:
        approval = db.get(Approval, approval_id)
    else:
        approval = db.scalars(
            select(Approval).where(Approval.plan_version_id == version.id,
                                   Approval.decision == "APPROVED")
            .order_by(Approval.id.desc()).limit(1)).first()
    if approval is None or approval.decision != "APPROVED":
        raise AppError("APPROVAL_REQUIRED", "This version has no approval.")
    current_hash = plan_hash(version.plan)
    if current_hash != version.content_hash or current_hash != approval.content_hash:
        raise AppError("APPROVAL_REQUIRED",
                       "The plan changed after it was approved. Approve it again.",
                       details={"reason": "content_hash_mismatch"})
    dry = db.get(DryRun, approval.dry_run_id) if approval.dry_run_id else None
    project = projects.get_project(db, version.project_id)
    if (dry is None or dry.result_hash != approval.dry_run_result_hash
            or dry.source_checksum != approval.source_checksum
            or project.source_checksum != approval.source_checksum):
        raise AppError("APPROVAL_REQUIRED",
                       "The approved dry run no longer matches. Approve it again.",
                       details={"reason": "dry_run_mismatch"})
    return approval, dry


def _reconcile_and_audit(db: Session, run: MigrationRun, actor_id: int) -> dict[str, Any]:
    result = reconcile(db, run)
    audit.record(db, project_id=run.project_id, entity_type="run", entity_id=run.id,
                 action="reconciliation.completed", actor_id=actor_id,
                 details={"status": result["status"], "run_status": run.status,
                          "discrepancies": [d["code"] for d in result["discrepancies"]]})
    db.commit()
    return result


def _run_attempt(
    db: Session, user: CurrentUser, run: MigrationRun, attempt: RunAttempt,
    version: PlanVersion, dry: DryRun, simulate_failure_after: int | None,
) -> dict[str, Any]:
    error: tuple[str, str] | None = None
    drift_rows: list[int] = []
    try:
        executor.process_attempt(
            db, run, attempt, plan=version.plan,
            source_rows=projects.source_rows(db, run.project_id),
            dry_run_id=dry.id, simulate_failure_after=simulate_failure_after,
        )
    except executor.FaultInjected as exc:
        error = ("FAULT_INJECTED", str(exc))
    except executor.DriftDetected as exc:
        db.rollback()
        drift_rows = exc.row_numbers
        error = ("DRIFT_DETECTED", str(exc))
    except SQLAlchemyError:
        db.rollback()
        log.exception("run.attempt.db_error", run_id=run.id, attempt=attempt.attempt_number)
        error = ("EXECUTION_ERROR", "A database error stopped this attempt.")

    now = utcnow()
    recompute_totals(db, run)
    attempt.finished_at = now
    if error is None:
        attempt.status = "COMPLETED"
        transition(db, run, "RUNNING", "COMPLETED", finished_at=now)
        action, details = "run.completed", {}
    else:
        attempt.status = "FAILED"
        attempt.error_code, attempt.error_message = error
        transition(db, run, "RUNNING", "FAILED")
        action = "run.attempt.failed"
        details = {"error_code": error[0], "drift_rows": drift_rows[:50]}
    audit.record(db, project_id=run.project_id, entity_type="run", entity_id=run.id,
                 action=action, actor_id=user.id,
                 details={"attempt_number": attempt.attempt_number, "kind": attempt.kind,
                          "inserted": run.inserted, "skipped_existing": run.skipped_existing,
                          "quarantined": run.quarantined, **details})
    db.commit()
    result = _reconcile_and_audit(db, run, user.id)
    if error is not None and error[0] == "DRIFT_DETECTED":
        raise AppError("DRIFT_DETECTED", "The data or plan no longer matches the approved dry run.",
                       details={"run_id": run.id, "row_numbers": drift_rows[:50]})
    return result


def execute(
    db: Session, user: CurrentUser, version: PlanVersion, idempotency_key: str,
    simulate_failure_after: int | None,
) -> tuple[dict[str, Any], bool]:
    """Returns (run body, replayed)."""
    fp = fingerprint(version.id, user.id)
    existing = db.scalars(select(MigrationRun)
                          .where(MigrationRun.idempotency_key == idempotency_key)).first()
    if existing is not None:
        if existing.request_fingerprint != fp:
            raise AppError("IDEMPOTENCY_KEY_REUSED",
                           "This Idempotency-Key was already used for a different request.")
        return run_out(db, existing, replayed=True), True

    approval, dry = _verified_approval(db, version)
    if simulate_failure_after is not None and not get_settings().fault_injection_enabled:
        raise AppError("VALIDATION_ERROR", "Fault injection is disabled on this server.")
    active = db.scalars(select(MigrationRun).where(
        MigrationRun.project_id == version.project_id,
        MigrationRun.status != "ROLLED_BACK").limit(1)).first()
    if active is not None:
        raise AppError("INVALID_STATE",
                       f"Run {active.id} is {active.status}; only one active run per project.",
                       details={"run_id": active.id, "run_status": active.status})

    run = MigrationRun(
        project_id=version.project_id, plan_version_id=version.id, approval_id=approval.id,
        idempotency_key=idempotency_key, request_fingerprint=fp, status="RUNNING",
        created_by=user.id,
    )
    db.add(run)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        again = db.scalars(select(MigrationRun)
                           .where(MigrationRun.idempotency_key == idempotency_key)).first()
        if again is not None and again.request_fingerprint == fp:
            return run_out(db, again, replayed=True), True
        raise AppError("INVALID_STATE", "Another run is already active for this project.") \
            from exc
    attempt = RunAttempt(run_id=run.id, attempt_number=1, kind="EXECUTE", status="RUNNING")
    db.add(attempt)
    db.flush()
    audit.record(db, project_id=run.project_id, entity_type="run", entity_id=run.id,
                 action="run.started", actor_id=user.id,
                 details={"plan_version_id": version.id, "approval_id": approval.id,
                          "dry_run_id": dry.id, "idempotency_key": idempotency_key,
                          "simulate_failure_after": simulate_failure_after})
    db.commit()
    reconciliation = _run_attempt(db, user, run, attempt, version, dry, simulate_failure_after)
    return run_out(db, run, reconciliation=reconciliation), False


def retry(db: Session, user: CurrentUser, run: MigrationRun) -> dict[str, Any]:
    if run.status != "FAILED":
        raise AppError("INVALID_STATE", f"Run {run.id} is {run.status}; only FAILED runs retry.",
                       details={"status": run.status})
    version = plans.get_version(db, run.plan_version_id)
    _, dry = _verified_approval(db, version, run.approval_id)
    transition(db, run, "FAILED", "RUNNING")
    number = (db.scalar(select(func.max(RunAttempt.attempt_number))
                        .where(RunAttempt.run_id == run.id)) or 0) + 1
    attempt = RunAttempt(run_id=run.id, attempt_number=number, kind="RETRY", status="RUNNING")
    db.add(attempt)
    db.flush()
    audit.record(db, project_id=run.project_id, entity_type="run", entity_id=run.id,
                 action="run.retry_started", actor_id=user.id,
                 details={"attempt_number": number})
    db.commit()
    reconciliation = _run_attempt(db, user, run, attempt, version, dry, None)
    return run_out(db, run, reconciliation=reconciliation)


def rollback(db: Session, user: CurrentUser, run: MigrationRun, reason: str) -> dict[str, Any]:
    """One transaction: CAS -> delete this run's rows -> rollbacks row -> CAS -> audit."""
    transition(db, run, ("COMPLETED", "FAILED"), "ROLLING_BACK")
    deleted = db.execute(
        delete(TgtCustomer).where(TgtCustomer.project_id == run.project_id,
                                  TgtCustomer.migration_run_id == run.id)
    ).rowcount
    rb = Rollback(run_id=run.id, actor_id=user.id, reason=reason, deleted_count=deleted or 0,
                  status="COMPLETED")
    db.add(rb)
    transition(db, run, "ROLLING_BACK", "ROLLED_BACK", finished_at=utcnow())
    audit.record(db, project_id=run.project_id, entity_type="run", entity_id=run.id,
                 action="rollback.completed", actor_id=user.id,
                 details={"deleted_count": deleted or 0, "reason": reason})
    db.commit()
    reconciliation = _reconcile_and_audit(db, run, user.id)
    return run_out(db, run, reconciliation=reconciliation,
                   rollback={"id": rb.id, "deleted_count": rb.deleted_count, "reason": reason})


def results_page(db: Session, run: MigrationRun, outcome: str | None, limit: int,
                 offset: int) -> dict[str, Any]:
    approval = db.get(Approval, run.approval_id)
    stmt = (
        select(RunRecordResult, SourceRecord.row_number, SourceRecord.source_key,
               RunAttempt.attempt_number, DryRunRecord.transformed)
        .join(SourceRecord, SourceRecord.id == RunRecordResult.source_record_id)
        .join(RunAttempt, RunAttempt.id == RunRecordResult.attempt_id)
        .outerjoin(DryRunRecord, (DryRunRecord.source_record_id == RunRecordResult.source_record_id)
                   & (DryRunRecord.dry_run_id == approval.dry_run_id))
        .where(RunRecordResult.run_id == run.id)
        .order_by(SourceRecord.row_number)
    )
    if outcome:
        stmt = stmt.where(RunRecordResult.outcome == outcome)
    rows = db.execute(stmt).all()
    items = [
        {"row_number": rn, "source_key": sk, "legacy_id": (tr or {}).get("legacy_id"),
         "outcome": r.outcome, "attempt_number": an, "errors": r.errors}
        for r, rn, sk, an, tr in rows
    ]
    return {"total": len(items), "items": items[offset:offset + limit]}


def target_records_page(db: Session, project_id: int, run_id: int | None, limit: int,
                        offset: int) -> dict[str, Any]:
    stmt = select(TgtCustomer).where(TgtCustomer.project_id == project_id)
    count = select(func.count()).select_from(TgtCustomer).where(
        TgtCustomer.project_id == project_id)
    if run_id is not None:
        stmt = stmt.where(TgtCustomer.migration_run_id == run_id)
        count = count.where(TgtCustomer.migration_run_id == run_id)
    rows = db.scalars(stmt.order_by(TgtCustomer.legacy_id).limit(limit).offset(offset)).all()
    return {
        "total": db.scalar(count) or 0,
        "items": [
            {**{c: getattr(t, c) for c in target_columns()}, "migration_run_id": t.migration_run_id,
             "row_hash": t.row_hash, "loaded_at": t.loaded_at}
            for t in rows
        ],
    }


def history(db: Session, project_id: int) -> dict[str, Any]:
    users = {u.id: u.username for u in db.scalars(select(User)).all()}
    events = db.scalars(select(AuditEvent).where(AuditEvent.project_id == project_id)
                        .order_by(AuditEvent.id.desc())).all()
    approvals = db.scalars(
        select(Approval).join(PlanVersion, PlanVersion.id == Approval.plan_version_id)
        .where(PlanVersion.project_id == project_id).order_by(Approval.id.desc())).all()
    run_rows = db.scalars(select(MigrationRun).where(MigrationRun.project_id == project_id)
                          .order_by(MigrationRun.id.desc())).all()
    rollbacks = db.scalars(
        select(Rollback).join(MigrationRun, MigrationRun.id == Rollback.run_id)
        .where(MigrationRun.project_id == project_id).order_by(Rollback.id.desc())).all()
    agent_runs = db.scalars(select(AgentRun).where(AgentRun.project_id == project_id)
                            .order_by(AgentRun.id.desc())).all()
    return {
        "events": [
            {"id": e.id, "entity_type": e.entity_type, "entity_id": e.entity_id,
             "action": e.action, "actor_id": e.actor_id, "actor": users.get(e.actor_id),
             "request_id": e.request_id, "details": e.details, "created_at": e.created_at}
            for e in events
        ],
        "approvals": [
            {"id": a.id, "plan_version_id": a.plan_version_id, "decision": a.decision,
             "actor": users.get(a.actor_id), "comment": a.comment,
             "self_approved": a.self_approved, "dry_run_id": a.dry_run_id,
             "created_at": a.created_at}
            for a in approvals
        ],
        "runs": [run_out(db, r) for r in run_rows],
        "rollbacks": [
            {"id": rb.id, "run_id": rb.run_id, "actor": users.get(rb.actor_id),
             "reason": rb.reason, "deleted_count": rb.deleted_count, "created_at": rb.created_at}
            for rb in rollbacks
        ],
        "agent_runs": [
            {"id": ar.id, "kind": ar.kind, "status": ar.status, "engine": ar.engine,
             "fell_back": ar.fell_back, "result_version_id": ar.result_version_id,
             "created_at": ar.created_at}
            for ar in agent_runs
        ],
    }


def _aware(ts: datetime | None) -> datetime | None:
    if ts is None:
        return None
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


def recover_stale_runs(db: Session, now: datetime | None = None) -> int:
    """Mark runs / agent runs stuck in RUNNING for more than 10 minutes as FAILED/INTERRUPTED."""
    now = now or utcnow()
    cutoff = now - STALE_AFTER
    recovered = 0
    for run in db.scalars(select(MigrationRun).where(MigrationRun.status == "RUNNING")).all():
        last = _aware(run.updated_at) or _aware(run.created_at)
        if last is None or last > cutoff:
            continue
        for attempt in _attempts(db, run.id):
            if attempt.status == "RUNNING":
                attempt.status = "FAILED"
                attempt.error_code = "INTERRUPTED"
                attempt.error_message = "The server restarted while this attempt was running."
                attempt.finished_at = now
        recompute_totals(db, run)
        transition(db, run, "RUNNING", "FAILED")
        audit.record(db, project_id=run.project_id, entity_type="run", entity_id=run.id,
                     action="run.interrupted", actor_id=None, details={"error_code": "INTERRUPTED"})
        recovered += 1
    for ar in db.scalars(select(AgentRun).where(AgentRun.status.in_(("QUEUED", "RUNNING")))).all():
        last = _aware(ar.started_at) or _aware(ar.created_at)
        if last is None or last > cutoff:
            continue
        ar.status = "FAILED"
        ar.error_code = "INTERRUPTED"
        ar.error_message = "The server restarted while this agent run was in progress."
        ar.finished_at = now
        audit.record(db, project_id=ar.project_id, entity_type="agent_run", entity_id=ar.id,
                     action="agent.run.interrupted", actor_id=None,
                     details={"error_code": "INTERRUPTED"})
        recovered += 1
    db.commit()
    return recovered
