from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.security import CurrentUser, get_current_user, require_role
from app.services import schema_imports

router = APIRouter(prefix="/schema-imports", tags=["schema-imports"])


class ReviewBody(BaseModel):
    normalized: dict[str, Any] | None = None
    comment: str | None = None


@router.post("", status_code=201)
def create_import(file: UploadFile = File(...), project_id: int | None = Form(default=None),
                  db: Session = Depends(get_db),
                  user: CurrentUser = Depends(require_role("operator"))) -> dict[str, Any]:
    """Upload a screenshot; the AI proposes a schema that a human must review."""
    data = file.file.read(schema_imports.MAX_BYTES + 1)
    return schema_imports.out(schema_imports.create(db, user, data, project_id))


@router.get("")
def list_imports(db: Session = Depends(get_db),
                 _user: CurrentUser = Depends(get_current_user)) -> list[dict[str, Any]]:
    return [schema_imports.out(i) for i in schema_imports.list_recent(db)]


@router.get("/{import_id}")
def get_import(import_id: int, db: Session = Depends(get_db),
               _user: CurrentUser = Depends(get_current_user)) -> dict[str, Any]:
    return schema_imports.out(schema_imports.get(db, import_id))


@router.post("/{import_id}/approve")
def approve_import(import_id: int, body: ReviewBody | None = None,
                   db: Session = Depends(get_db),
                   user: CurrentUser = Depends(require_role("approver"))) -> dict[str, Any]:
    body = body or ReviewBody()
    return schema_imports.out(schema_imports.decide(db, user, import_id, True, body.normalized))


@router.post("/{import_id}/reject")
def reject_import(import_id: int, body: ReviewBody | None = None,
                  db: Session = Depends(get_db),
                  user: CurrentUser = Depends(require_role("approver"))) -> dict[str, Any]:
    return schema_imports.out(schema_imports.decide(db, user, import_id, False, None))
