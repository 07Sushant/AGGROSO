from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app import logging as app_logging
from app.schemas.api import LogsResponse
from app.security import get_current_user

router = APIRouter(prefix="/ops", tags=["ops"], dependencies=[Depends(get_current_user)])


@router.get("/logs", response_model=LogsResponse)
def logs(
    request_id: str | None = Query(default=None, max_length=64),
    event: str | None = Query(default=None, max_length=80),
    limit: int = Query(default=200, ge=1, le=1000),
) -> LogsResponse:
    """Recent structured log lines (newest first), already redacted and alias-only."""
    items = app_logging.log_buffer.query(request_id=request_id, event=event, limit=limit)
    return LogsResponse(items=items, count=len(items))
