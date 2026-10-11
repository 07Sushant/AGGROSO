"""State machines for plan versions and migration runs (spec §6.3).

Every transition is a compare-and-set: ``UPDATE ... SET status=:new WHERE id=:id AND status IN
(:expected)``. If the row count is not 1 the caller gets 409 ``INVALID_STATE``.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import MigrationRun, PlanVersion

PLAN_TRANSITIONS: set[tuple[str, str]] = {
    ("DRAFT", "APPROVED"),
    ("DRAFT", "REJECTED"),
    ("APPROVED", "DRAFT"),  # revoke
    ("APPROVED", "SUPERSEDED"),
}

RUN_TRANSITIONS: set[tuple[str, str]] = {
    ("RUNNING", "COMPLETED"),
    ("RUNNING", "FAILED"),
    ("FAILED", "RUNNING"),  # retry
    ("COMPLETED", "ROLLING_BACK"),
    ("FAILED", "ROLLING_BACK"),
    ("ROLLING_BACK", "ROLLED_BACK"),
}

_TABLES: dict[type, set[tuple[str, str]]] = {
    PlanVersion: PLAN_TRANSITIONS,
    MigrationRun: RUN_TRANSITIONS,
}


def transition(
    db: Session,
    obj: PlanVersion | MigrationRun,
    expected: str | tuple[str, ...],
    new: str,
    **values: Any,
) -> None:
    model = type(obj)
    allowed = _TABLES[model]
    expected_set = (expected,) if isinstance(expected, str) else expected
    for exp in expected_set:
        if (exp, new) not in allowed:
            raise ValueError(f"{model.__name__}: {exp} -> {new} is not a valid transition")
    result = db.execute(
        update(model)
        .where(model.id == obj.id, model.status.in_(expected_set))
        .values(status=new, **values)
        .execution_options(synchronize_session="evaluate")
    )
    if result.rowcount != 1:
        db.rollback()
        raise AppError(
            "INVALID_STATE",
            f"{model.__name__} {obj.id} is not in state {' or '.join(expected_set)}.",
            details={"expected": list(expected_set), "target": new},
        )
