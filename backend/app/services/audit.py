"""Append-only audit events (a PostgreSQL trigger blocks UPDATE/DELETE). Also logged."""

from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy.orm import Session

from app.logging import get_logger
from app.models import AuditEvent

log = get_logger("app")


def record(
    db: Session,
    *,
    project_id: int | None,
    entity_type: str,
    entity_id: int | str,
    action: str,
    actor_id: int | None,
    details: dict[str, Any] | None = None,
) -> AuditEvent:
    """Add an audit event to the current transaction (the caller commits)."""
    request_id = structlog.contextvars.get_contextvars().get("request_id")
    event = AuditEvent(
        project_id=project_id,
        entity_type=entity_type,
        entity_id=str(entity_id),
        action=action,
        actor_id=actor_id,
        request_id=request_id,
        details=details or {},
    )
    db.add(event)
    log.info(action, project_id=project_id, entity_type=entity_type, entity_id=str(entity_id),
             details=details or {})
    return event
