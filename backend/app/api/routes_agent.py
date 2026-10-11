from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.api import AgentRunCreate
from app.security import CurrentUser, get_current_user, require_role
from app.services import agent_runs, projects

router = APIRouter(tags=["agent"])


@router.post("/projects/{project_id}/agent-runs", status_code=202)
def start_agent_run(project_id: int, body: AgentRunCreate | None = None,
                    db: Session = Depends(get_db),
                    user: CurrentUser = Depends(require_role("operator"))) -> dict[str, Any]:
    """Queue an agent run (background job). Poll GET /agent-runs/{id} for the live trace."""
    body = body or AgentRunCreate()
    project = projects.get_project(db, project_id)
    run = agent_runs.create_agent_run(db, user, project, body.base_version_id, body.use_answers)
    return agent_runs.agent_run_out(db, run)


@router.get("/agent-runs/{run_id}")
def get_agent_run(run_id: int, since_step: int = Query(default=0, ge=0),
                  db: Session = Depends(get_db),
                  _user: CurrentUser = Depends(get_current_user)) -> dict[str, Any]:
    return agent_runs.agent_run_out(db, agent_runs.get_agent_run(db, run_id),
                                    since_step=since_step)
