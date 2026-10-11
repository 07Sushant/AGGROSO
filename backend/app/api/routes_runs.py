from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.db import get_db
from app.domain.reconciliation import reconcile
from app.schemas.api import RollbackRequest
from app.security import CurrentUser, get_current_user, require_role
from app.services import dry_runs, runs

router = APIRouter(tags=["runs"])


@router.get("/dry-runs/{dry_run_id}")
def get_dry_run(dry_run_id: int, db: Session = Depends(get_db),
                _user: CurrentUser = Depends(get_current_user)) -> dict[str, Any]:
    return dry_runs.dry_run_out(db, dry_runs.get_dry_run(db, dry_run_id))


@router.get("/dry-runs/{dry_run_id}/records")
def dry_run_records(
    dry_run_id: int,
    outcome: Literal["ACCEPTED", "REJECTED"] | None = None,
    code: str | None = Query(default=None, max_length=64),
    target_field: str | None = Query(default=None, max_length=64),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    dry_runs.get_dry_run(db, dry_run_id)
    return dry_runs.records_page(db, dry_run_id, outcome=outcome, code=code,
                                 target_field=target_field, limit=limit, offset=offset)


@router.get("/dry-runs/{dry_run_id}/export")
def export_quarantine(dry_run_id: int, format: Literal["csv", "json"] = "csv",
                      db: Session = Depends(get_db),
                      _user: CurrentUser = Depends(get_current_user)) -> Response:
    dry_runs.get_dry_run(db, dry_run_id)
    content, media_type = dry_runs.export(db, dry_run_id, format)
    filename = f"dry-run-{dry_run_id}-quarantine.{format}"
    return Response(content=content, media_type=media_type,
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/runs/{run_id}")
def get_run(run_id: int, db: Session = Depends(get_db),
            _user: CurrentUser = Depends(get_current_user)) -> dict[str, Any]:
    return runs.run_out(db, runs.get_run(db, run_id))


@router.get("/runs/{run_id}/results")
def run_results(
    run_id: int,
    outcome: Literal["INSERTED", "SKIPPED_EXISTING", "QUARANTINED"] | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    return runs.results_page(db, runs.get_run(db, run_id), outcome, limit, offset)


@router.get("/runs/{run_id}/reconciliation")
def run_reconciliation(run_id: int, db: Session = Depends(get_db),
                       _user: CurrentUser = Depends(get_current_user)) -> dict[str, Any]:
    return reconcile(db, runs.get_run(db, run_id))


@router.post("/runs/{run_id}/retry")
def retry(run_id: int, db: Session = Depends(get_db),
          user: CurrentUser = Depends(require_role("operator"))) -> dict[str, Any]:
    return runs.retry(db, user, runs.get_run(db, run_id))


@router.post("/runs/{run_id}/rollback")
def rollback(run_id: int, body: RollbackRequest, db: Session = Depends(get_db),
             user: CurrentUser = Depends(require_role("approver"))) -> dict[str, Any]:
    return runs.rollback(db, user, runs.get_run(db, run_id), body.reason.strip())
