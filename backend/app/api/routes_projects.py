from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.api import PlanVersionCreate, ProjectCreate
from app.security import CurrentUser, get_current_user, require_role
from app.services import plans, projects, runs

router = APIRouter(prefix="/projects", tags=["projects"])

# Editing a plan (new version, answers, risk acks) is open to both roles, so an approver can
# also author a version; approving their own edit is then flagged as self-approval.
plan_editor = require_role("operator", "approver")


@router.post("", status_code=201)
def create_project(body: ProjectCreate, db: Session = Depends(get_db),
                   user: CurrentUser = Depends(require_role("operator"))) -> dict[str, Any]:
    project = projects.create_project(db, user, body.name, body.dataset_key)
    return projects.project_out(db, project, detail=True)


@router.get("")
def list_projects(db: Session = Depends(get_db),
                  _user: CurrentUser = Depends(get_current_user)) -> list[dict[str, Any]]:
    return projects.list_projects(db)


@router.get("/{project_id}")
def get_project(project_id: int, db: Session = Depends(get_db),
                _user: CurrentUser = Depends(get_current_user)) -> dict[str, Any]:
    return projects.project_out(db, projects.get_project(db, project_id), detail=True)


@router.get("/{project_id}/source-records")
def source_records(project_id: int, limit: int = Query(default=50, ge=1, le=500),
                   offset: int = Query(default=0, ge=0), db: Session = Depends(get_db),
                   _user: CurrentUser = Depends(get_current_user)) -> dict[str, Any]:
    projects.get_project(db, project_id)
    return projects.source_records_page(db, project_id, limit, offset)


@router.get("/{project_id}/plan-versions")
def list_plan_versions(project_id: int, db: Session = Depends(get_db),
                       _user: CurrentUser = Depends(get_current_user)) -> list[dict[str, Any]]:
    projects.get_project(db, project_id)
    return plans.list_versions(db, project_id)


@router.post("/{project_id}/plan-versions", status_code=201)
def create_plan_version(project_id: int, body: PlanVersionCreate, db: Session = Depends(get_db),
                        user: CurrentUser = Depends(plan_editor)) -> dict[str, Any]:
    project = projects.get_project(db, project_id)
    version = plans.create_version(
        db, project=project, raw_plan=body.plan, author_type="human", author_id=user.id,
        change_note=body.change_note.strip(), parent_version_id=body.parent_version_id,
    )
    return plans.version_out(db, version)


@router.post("/{project_id}/plan-versions/reference", status_code=201)
def load_reference_plan(project_id: int, db: Session = Depends(get_db),
                        user: CurrentUser = Depends(require_role("operator"))) -> dict[str, Any]:
    project = projects.get_project(db, project_id)
    return plans.version_out(db, plans.load_reference(db, user, project))


@router.get("/{project_id}/target-records")
def target_records(project_id: int, run_id: int | None = None,
                   limit: int = Query(default=50, ge=1, le=500),
                   offset: int = Query(default=0, ge=0), db: Session = Depends(get_db),
                   _user: CurrentUser = Depends(get_current_user)) -> dict[str, Any]:
    projects.get_project(db, project_id)
    return runs.target_records_page(db, project_id, run_id, limit, offset)


@router.get("/{project_id}/history")
def history(project_id: int, db: Session = Depends(get_db),
            _user: CurrentUser = Depends(get_current_user)) -> dict[str, Any]:
    projects.get_project(db, project_id)
    return runs.history(db, project_id)
