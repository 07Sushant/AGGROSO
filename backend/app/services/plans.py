"""Immutable plan versions, diffs, clarification answers and risk acknowledgements."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.agent.plan_validator import validate_plan
from app.domain.hashing import plan_hash
from app.errors import AppError
from app.models import ClarificationAnswer, PlanVersion, Project, RiskAcknowledgement, User
from app.schemas.plan import normalize_plan
from app.security import CurrentUser
from app.services import audit, inputs

REFERENCE_NOTE = "Loaded the reference plan"


def get_version(db: Session, version_id: int) -> PlanVersion:
    version = db.get(PlanVersion, version_id)
    if version is None:
        raise AppError("NOT_FOUND", f"Plan version {version_id} was not found.")
    return version


def answers_for(db: Session, version_id: int) -> dict[str, str]:
    rows = db.scalars(
        select(ClarificationAnswer).where(ClarificationAnswer.plan_version_id == version_id)
    ).all()
    return {r.question_id: r.answer for r in rows}


def acks_for(db: Session, version_id: int) -> list[str]:
    return sorted(db.scalars(
        select(RiskAcknowledgement.risk_id).where(
            RiskAcknowledgement.plan_version_id == version_id)
    ).all())


def open_items(
    plan: dict[str, Any], answers: dict[str, str], acks: list[str]
) -> tuple[list[str], list[str]]:
    """(unanswered question ids, unacknowledged high-severity risk ids)."""
    unanswered = [q["id"] for q in plan.get("clarification_questions", [])
                  if not answers.get(q["id"], "").strip()]
    high = [r["id"] for m in plan.get("mappings", []) for r in m.get("risks", [])
            if r.get("severity") == "high"]
    return unanswered, [r for r in high if r not in set(acks)]


def version_out(db: Session, v: PlanVersion, *, include_plan: bool = True) -> dict[str, Any]:
    answers = answers_for(db, v.id)
    acks = acks_for(db, v.id)
    unanswered, unacked = open_items(v.plan, answers, acks)
    author = db.get(User, v.author_id) if v.author_id else None
    out: dict[str, Any] = {
        "id": v.id,
        "project_id": v.project_id,
        "version_number": v.version_number,
        "parent_version_id": v.parent_version_id,
        "author_type": v.author_type,
        "author_id": v.author_id,
        "author_username": author.username if author else None,
        "status": v.status,
        "content_hash": v.content_hash,
        "change_note": v.change_note,
        "agent_run_id": v.agent_run_id,
        "created_at": v.created_at,
        "answers": answers,
        "risk_acks": acks,
        "unanswered_question_ids": unanswered,
        "unacknowledged_high_risk_ids": unacked,
    }
    if include_plan:
        out["plan"] = v.plan
    return out


def list_versions(db: Session, project_id: int) -> list[dict[str, Any]]:
    versions = db.scalars(
        select(PlanVersion).where(PlanVersion.project_id == project_id)
        .order_by(PlanVersion.version_number.desc())
    ).all()
    return [version_out(db, v, include_plan=False) for v in versions]


def create_version(
    db: Session,
    *,
    project: Project,
    raw_plan: Any,
    author_type: str,
    author_id: int | None,
    change_note: str | None,
    parent_version_id: int | None = None,
    agent_run_id: int | None = None,
    commit: bool = True,
) -> PlanVersion:
    """Validate and store a new DRAFT version. Invalid plans are rejected, never auto-fixed."""
    validation = validate_plan(raw_plan)
    if not validation.valid or validation.plan is None:
        raise AppError("VALIDATION_ERROR", "The plan is not valid.",
                       details={"errors": validation.errors})
    plan = normalize_plan(validation.plan)

    if parent_version_id is not None:
        parent = get_version(db, parent_version_id)
        if parent.project_id != project.id:
            raise AppError("VALIDATION_ERROR", "The parent version belongs to another project.")
    else:
        parent = db.scalars(
            select(PlanVersion).where(PlanVersion.project_id == project.id)
            .order_by(PlanVersion.version_number.desc()).limit(1)
        ).first()

    number = (db.scalar(
        select(func.max(PlanVersion.version_number)).where(PlanVersion.project_id == project.id)
    ) or 0) + 1
    version = PlanVersion(
        project_id=project.id,
        version_number=number,
        parent_version_id=parent.id if parent else None,
        author_type=author_type,
        author_id=author_id,
        status="DRAFT",
        plan=plan,
        content_hash=plan_hash(plan),
        change_note=change_note,
        agent_run_id=agent_run_id,
    )
    db.add(version)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise AppError("INVALID_STATE", "Another version was saved at the same time; retry.") \
            from exc

    carried: list[str] = []
    if parent is not None:
        question_ids = {q["id"] for q in plan["clarification_questions"]}
        for qid, answer in answers_for(db, parent.id).items():
            if qid in question_ids:
                db.add(ClarificationAnswer(
                    plan_version_id=version.id, question_id=qid, answer=answer,
                    answered_by=author_id or project.created_by))
                carried.append(qid)
        db.flush()

    audit.record(db, project_id=project.id, entity_type="plan_version", entity_id=version.id,
                 action="plan_version.created", actor_id=author_id,
                 details={"version_number": number, "author_type": author_type,
                          "parent_version_id": version.parent_version_id,
                          "content_hash": version.content_hash,
                          "answers_carried_forward": sorted(carried),
                          "warnings": validation.warnings})
    if commit:
        db.commit()
    return version


def load_reference(db: Session, user: CurrentUser, project: Project) -> PlanVersion:
    ref = inputs.reference_plan()
    version = create_version(db, project=project, raw_plan=ref["plan"], author_type="human",
                             author_id=user.id, change_note=REFERENCE_NOTE, commit=False)
    existing = {
        r.question_id: r
        for r in db.scalars(select(ClarificationAnswer)
                            .where(ClarificationAnswer.plan_version_id == version.id)).all()
    }
    for qid, answer in ref["reference_answers"].items():
        if qid in existing:  # the reference answers replace carried-forward ones
            existing[qid].answer = answer
            existing[qid].answered_by = user.id
        else:
            db.add(ClarificationAnswer(plan_version_id=version.id, question_id=qid,
                                       answer=answer, answered_by=user.id))
    db.commit()
    return version


def _require_draft(v: PlanVersion) -> None:
    if v.status != "DRAFT":
        raise AppError("INVALID_STATE", f"Version {v.version_number} is {v.status}; only a DRAFT "
                       "version can be changed.", details={"status": v.status})


def save_answers(
    db: Session, user: CurrentUser, v: PlanVersion, answers: dict[str, str]
) -> None:
    _require_draft(v)
    known = {q["id"] for q in v.plan.get("clarification_questions", [])}
    unknown = sorted(set(answers) - known)
    if unknown:
        raise AppError("VALIDATION_ERROR", "Some answers refer to unknown questions.",
                       details={"unknown_question_ids": unknown})
    existing = {
        r.question_id: r
        for r in db.scalars(select(ClarificationAnswer)
                            .where(ClarificationAnswer.plan_version_id == v.id)).all()
    }
    for qid, answer in answers.items():
        if qid in existing:
            existing[qid].answer = answer
            existing[qid].answered_by = user.id
        else:
            db.add(ClarificationAnswer(plan_version_id=v.id, question_id=qid, answer=answer,
                                       answered_by=user.id))
    audit.record(db, project_id=v.project_id, entity_type="plan_version", entity_id=v.id,
                 action="plan.answers_saved", actor_id=user.id,
                 details={"question_ids": sorted(answers)})
    db.commit()


def acknowledge_risks(db: Session, user: CurrentUser, v: PlanVersion, risk_ids: list[str]) -> None:
    _require_draft(v)
    known = {r["id"] for m in v.plan.get("mappings", []) for r in m.get("risks", [])}
    unknown = sorted(set(risk_ids) - known)
    if unknown:
        raise AppError("VALIDATION_ERROR", "Some risk ids are not in this plan.",
                       details={"unknown_risk_ids": unknown})
    already = set(acks_for(db, v.id))
    new = sorted(set(risk_ids) - already)
    for rid in new:
        db.add(RiskAcknowledgement(plan_version_id=v.id, risk_id=rid, acknowledged_by=user.id))
    if new:
        audit.record(db, project_id=v.project_id, entity_type="plan_version", entity_id=v.id,
                     action="plan.risks_acknowledged", actor_id=user.id,
                     details={"risk_ids": new})
    db.commit()


_SECTIONS = ("key", "unmapped_source_fields", "unmapped_target_fields", "incompatibilities",
             "clarification_questions", "risk_summary")


def diff_plans(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    """Field-level diff. Mappings are matched by target field."""
    old_maps = {m["target_field"]: m for m in old.get("mappings", [])}
    new_maps = {m["target_field"]: m for m in new.get("mappings", [])}
    changes: list[dict[str, Any]] = []
    unchanged = 0
    for target in sorted(set(old_maps) | set(new_maps)):
        a, b = old_maps.get(target), new_maps.get(target)
        if a is None:
            changes.append({"target_field": target, "change": "added", "to": b})
        elif b is None:
            changes.append({"target_field": target, "change": "removed", "from": a})
        else:
            fields = {k: {"from": a.get(k), "to": b.get(k)}
                      for k in sorted(set(a) | set(b)) if a.get(k) != b.get(k)}
            if fields:
                changes.append({"target_field": target, "change": "changed", "fields": fields})
            else:
                unchanged += 1
    sections = {s: {"from": old.get(s), "to": new.get(s)}
                for s in _SECTIONS if old.get(s) != new.get(s)}
    summary = {
        "added": sum(1 for c in changes if c["change"] == "added"),
        "removed": sum(1 for c in changes if c["change"] == "removed"),
        "changed": sum(1 for c in changes if c["change"] == "changed"),
        "unchanged": unchanged,
    }
    return {"mappings": changes, "sections": sections, "summary": summary}


def diff_versions(db: Session, v: PlanVersion, against_id: int | None) -> dict[str, Any]:
    base_id = against_id if against_id is not None else v.parent_version_id
    if base_id is None:
        return {"version_id": v.id, "against_version_id": None,
                **diff_plans({}, v.plan)}
    base = get_version(db, base_id)
    if base.project_id != v.project_id:
        raise AppError("VALIDATION_ERROR", "Both versions must belong to the same project.")
    return {"version_id": v.id, "against_version_id": base.id, **diff_plans(base.plan, v.plan)}
