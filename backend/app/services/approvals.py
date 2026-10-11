"""Server-enforced approval gate (spec §6.4): checklist, approve, reject, revoke.

Self-approval is a warning, not a block: it is recorded as ``self_approved=true``.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.hashing import plan_hash
from app.domain.state import transition
from app.errors import AppError
from app.models import Approval, MigrationRun, PlanVersion
from app.security import CurrentUser
from app.services import audit, dry_runs, plans, projects


def latest_approval(db: Session, version_id: int) -> Approval | None:
    return db.scalars(
        select(Approval).where(Approval.plan_version_id == version_id,
                               Approval.decision == "APPROVED")
        .order_by(Approval.id.desc()).limit(1)
    ).first()


def checklist(db: Session, version: PlanVersion, user: CurrentUser) -> dict[str, Any]:
    project = projects.get_project(db, version.project_id)
    dry = dry_runs.latest_for_version(db, version.id)
    answers = plans.answers_for(db, version.id)
    acks = plans.acks_for(db, version.id)
    unanswered, unacked = plans.open_items(version.plan, answers, acks)
    self_approval = version.author_type == "human" and version.author_id == user.id

    items = [
        {"id": "role", "label": "You have the approver role",
         "ok": user.role == "approver", "blocking": True,
         "detail": None if user.role == "approver" else f"Your role is {user.role}."},
        {"id": "status", "label": "The version is a DRAFT",
         "ok": version.status == "DRAFT", "blocking": True,
         "detail": None if version.status == "DRAFT" else f"The version is {version.status}."},
        {"id": "integrity", "label": "The plan matches its recorded hash",
         "ok": plan_hash(version.plan) == version.content_hash, "blocking": True, "detail": None},
        {"id": "dry_run", "label": "A dry run of this exact version exists on the current data",
         "ok": dry is not None and dry.source_checksum == project.source_checksum,
         "blocking": True,
         "detail": ("No dry run yet." if dry is None else
                    None if dry.source_checksum == project.source_checksum else
                    "The latest dry run used different source data.")},
        {"id": "questions", "label": "Every clarification question is answered",
         "ok": not unanswered, "blocking": True, "missing": unanswered,
         "detail": f"Unanswered: {', '.join(unanswered)}" if unanswered else None},
        {"id": "high_risks", "label": "Every high-severity risk is acknowledged",
         "ok": not unacked, "blocking": True, "missing": unacked,
         "detail": f"Not acknowledged: {', '.join(unacked)}" if unacked else None},
        {"id": "separation_of_duties", "label": "Approver is not the author of this version",
         "ok": not self_approval, "blocking": False,
         "detail": "Self-approval: you edited this version." if self_approval else None},
    ]
    blockers = [i["id"] for i in items if i["blocking"] and not i["ok"]]
    return {
        "plan_version_id": version.id,
        "content_hash": version.content_hash,
        "dry_run": (
            {"id": dry.id, "result_hash": dry.result_hash,
             "counts": {"source": dry.source_count, "transformed": dry.transformed_count,
                        "accepted": dry.accepted_count, "rejected": dry.rejected_count}}
            if dry else None
        ),
        "items": items,
        "blockers": blockers,
        "can_approve": not blockers,
        "self_approval": self_approval,
        "unanswered_question_ids": unanswered,
        "unacknowledged_high_risk_ids": unacked,
    }


def approval_out(a: Approval) -> dict[str, Any]:
    return {
        "id": a.id, "plan_version_id": a.plan_version_id, "decision": a.decision,
        "actor_id": a.actor_id, "comment": a.comment, "content_hash": a.content_hash,
        "dry_run_id": a.dry_run_id, "dry_run_result_hash": a.dry_run_result_hash,
        "source_checksum": a.source_checksum, "self_approved": a.self_approved,
        "created_at": a.created_at,
    }


def approve(db: Session, user: CurrentUser, version: PlanVersion, comment: str | None) -> Approval:
    check = checklist(db, version, user)
    if not check["can_approve"]:
        raise AppError(
            "INVALID_STATE", "The approval checklist is not complete.",
            details={"blockers": check["blockers"],
                     "unanswered_question_ids": check["unanswered_question_ids"],
                     "unacknowledged_high_risk_ids": check["unacknowledged_high_risk_ids"]},
        )
    dry = dry_runs.latest_for_version(db, version.id)
    assert dry is not None  # guaranteed by the checklist
    for other in db.scalars(select(PlanVersion).where(
            PlanVersion.project_id == version.project_id, PlanVersion.status == "APPROVED",
            PlanVersion.id != version.id)).all():
        transition(db, other, "APPROVED", "SUPERSEDED")
        audit.record(db, project_id=version.project_id, entity_type="plan_version",
                     entity_id=other.id, action="plan.superseded", actor_id=user.id,
                     details={"superseded_by": version.id})
    transition(db, version, "DRAFT", "APPROVED")
    approval = Approval(
        plan_version_id=version.id, decision="APPROVED", actor_id=user.id, comment=comment,
        content_hash=version.content_hash, dry_run_id=dry.id, dry_run_result_hash=dry.result_hash,
        source_checksum=dry.source_checksum, self_approved=check["self_approval"],
    )
    db.add(approval)
    db.flush()
    audit.record(db, project_id=version.project_id, entity_type="plan_version",
                 entity_id=version.id, action="plan.approved", actor_id=user.id,
                 details={"approval_id": approval.id, "content_hash": version.content_hash,
                          "dry_run_id": dry.id, "dry_run_result_hash": dry.result_hash,
                          "self_approved": check["self_approval"], "comment": comment})
    db.commit()
    return approval


def reject(db: Session, user: CurrentUser, version: PlanVersion, comment: str) -> Approval:
    transition(db, version, "DRAFT", "REJECTED")
    dry = dry_runs.latest_for_version(db, version.id)
    approval = Approval(
        plan_version_id=version.id, decision="REJECTED", actor_id=user.id, comment=comment,
        content_hash=version.content_hash, dry_run_id=dry.id if dry else None,
        dry_run_result_hash=dry.result_hash if dry else None,
        source_checksum=dry.source_checksum if dry else None,
    )
    db.add(approval)
    db.flush()
    audit.record(db, project_id=version.project_id, entity_type="plan_version",
                 entity_id=version.id, action="plan.rejected", actor_id=user.id,
                 details={"approval_id": approval.id, "comment": comment})
    db.commit()
    return approval


def revoke(db: Session, user: CurrentUser, version: PlanVersion, comment: str) -> Approval:
    active = db.scalars(select(MigrationRun).where(
        MigrationRun.plan_version_id == version.id,
        MigrationRun.status != "ROLLED_BACK").limit(1)).first()
    if active is not None:
        raise AppError("INVALID_STATE",
                       f"Run {active.id} for this version is {active.status}; roll it back first.",
                       details={"run_id": active.id, "run_status": active.status})
    transition(db, version, "APPROVED", "DRAFT")
    approval = Approval(
        plan_version_id=version.id, decision="REVOKED", actor_id=user.id, comment=comment,
        content_hash=version.content_hash,
    )
    db.add(approval)
    db.flush()
    audit.record(db, project_id=version.project_id, entity_type="plan_version",
                 entity_id=version.id, action="plan.revoked", actor_id=user.id,
                 details={"approval_id": approval.id, "comment": comment})
    db.commit()
    return approval
