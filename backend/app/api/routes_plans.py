from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Depends, Header, Response
from sqlalchemy.orm import Session

from app.agent.plan_validator import validate_plan
from app.api.routes_projects import plan_editor
from app.db import get_db
from app.errors import AppError
from app.schemas.api import (
    AnswersRequest,
    ApproveRequest,
    CommentRequired,
    ExecuteRequest,
    PlanValidateRequest,
    RiskAckRequest,
)
from app.security import CurrentUser, get_current_user, require_role
from app.services import approvals, dry_runs, plans, runs

router = APIRouter(prefix="/plan-versions", tags=["plans"])

_IDEMPOTENCY_KEY_RE = re.compile(r"^[A-Za-z0-9._:\-]{8,128}$")


@router.get("/{version_id}")
def get_version(version_id: int, db: Session = Depends(get_db),
                _user: CurrentUser = Depends(get_current_user)) -> dict[str, Any]:
    return plans.version_out(db, plans.get_version(db, version_id))


@router.get("/{version_id}/diff")
def diff(version_id: int, against: int | None = None, db: Session = Depends(get_db),
         _user: CurrentUser = Depends(get_current_user)) -> dict[str, Any]:
    return plans.diff_versions(db, plans.get_version(db, version_id), against)


@router.post("/{version_id}/validate")
def validate(version_id: int, body: PlanValidateRequest | None = None,
             db: Session = Depends(get_db),
             _user: CurrentUser = Depends(plan_editor)) -> dict[str, Any]:
    """Validate a candidate plan (body) or the stored plan. Nothing is stored."""
    version = plans.get_version(db, version_id)
    candidate = body.plan if body is not None and body.plan is not None else version.plan
    return validate_plan(candidate).to_dict()


@router.post("/{version_id}/answers")
def save_answers(version_id: int, body: AnswersRequest, db: Session = Depends(get_db),
                 user: CurrentUser = Depends(plan_editor)) -> dict[str, Any]:
    version = plans.get_version(db, version_id)
    plans.save_answers(db, user, version, {k: v.strip() for k, v in body.answers.items()})
    return plans.version_out(db, version)


@router.post("/{version_id}/risk-acks")
def acknowledge_risks(version_id: int, body: RiskAckRequest, db: Session = Depends(get_db),
                      user: CurrentUser = Depends(plan_editor)) -> dict[str, Any]:
    version = plans.get_version(db, version_id)
    plans.acknowledge_risks(db, user, version, body.risk_ids)
    return plans.version_out(db, version)


@router.post("/{version_id}/dry-runs", status_code=201)
def create_dry_run(version_id: int, db: Session = Depends(get_db),
                   user: CurrentUser = Depends(require_role("operator"))) -> dict[str, Any]:
    version = plans.get_version(db, version_id)
    return dry_runs.dry_run_out(db, dry_runs.create_dry_run(db, user, version))


@router.post("/{version_id}/determinism")
def determinism(version_id: int, db: Session = Depends(get_db),
                _user: CurrentUser = Depends(require_role("operator"))) -> dict[str, Any]:
    return dry_runs.determinism_check(db, plans.get_version(db, version_id))


@router.get("/{version_id}/approval-checklist")
def approval_checklist(version_id: int, db: Session = Depends(get_db),
                       user: CurrentUser = Depends(get_current_user)) -> dict[str, Any]:
    return approvals.checklist(db, plans.get_version(db, version_id), user)


@router.post("/{version_id}/approve")
def approve(version_id: int, body: ApproveRequest | None = None, db: Session = Depends(get_db),
            user: CurrentUser = Depends(require_role("approver"))) -> dict[str, Any]:
    version = plans.get_version(db, version_id)
    approval = approvals.approve(db, user, version, body.comment if body else None)
    return {"approval": approvals.approval_out(approval), "version": plans.version_out(db, version)}


@router.post("/{version_id}/reject")
def reject(version_id: int, body: CommentRequired, db: Session = Depends(get_db),
           user: CurrentUser = Depends(require_role("approver"))) -> dict[str, Any]:
    version = plans.get_version(db, version_id)
    approval = approvals.reject(db, user, version, body.comment.strip())
    return {"approval": approvals.approval_out(approval), "version": plans.version_out(db, version)}


@router.post("/{version_id}/revoke")
def revoke(version_id: int, body: CommentRequired, db: Session = Depends(get_db),
           user: CurrentUser = Depends(require_role("approver"))) -> dict[str, Any]:
    version = plans.get_version(db, version_id)
    approval = approvals.revoke(db, user, version, body.comment.strip())
    return {"approval": approvals.approval_out(approval), "version": plans.version_out(db, version)}


@router.post("/{version_id}/runs", status_code=201)
def execute(version_id: int, response: Response, body: ExecuteRequest | None = None,
            idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
            db: Session = Depends(get_db),
            user: CurrentUser = Depends(require_role("operator"))) -> dict[str, Any]:
    if not idempotency_key or not _IDEMPOTENCY_KEY_RE.match(idempotency_key):
        raise AppError("VALIDATION_ERROR",
                       "An Idempotency-Key header (8-128 letters, digits, '.', '_', ':', '-') "
                       "is required.", details={"header": "Idempotency-Key"})
    version = plans.get_version(db, version_id)
    body_out, replayed = runs.execute(
        db, user, version, idempotency_key, body.simulate_failure_after if body else None)
    if replayed:
        response.status_code = 200
    return body_out
