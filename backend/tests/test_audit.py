from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.models import AuditEvent
from tests import flow


def test_gate_actions_write_audit_events(client, operator_headers, approver_headers):  # type: ignore[no-untyped-def]
    project, version = flow.approved_version(client, operator_headers, approver_headers,
                                             "clean_25")
    run = flow.execute(client, operator_headers, version["id"],
                       simulate_failure_after=5).json()
    client.post(f"/api/runs/{run['id']}/retry", headers=operator_headers)
    client.post(f"/api/runs/{run['id']}/rollback", json={"reason": "audit test"},
                headers=approver_headers)
    history = client.get(f"/api/projects/{project['id']}/history",
                         headers=operator_headers).json()
    actions = [e["action"] for e in reversed(history["events"])]
    expected = ["project.created", "plan_version.created", "plan.risks_acknowledged",
                "dry_run.completed", "plan.approved", "run.started", "run.attempt.failed",
                "reconciliation.completed", "run.retry_started", "run.completed",
                "reconciliation.completed", "rollback.completed", "reconciliation.completed"]
    assert actions == expected
    assert all(e["request_id"] for e in history["events"])
    approved = next(e for e in history["events"] if e["action"] == "plan.approved")
    assert approved["actor"] == "approver"
    assert history["runs"][0]["status"] == "ROLLED_BACK"
    assert len(history["runs"][0]["attempts"]) == 2
    assert history["rollbacks"][0]["reason"] == "audit test"
    assert [a["decision"] for a in history["approvals"]] == ["APPROVED"]


def _audit_trigger_sql() -> tuple[str, list[str]]:
    path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0001_initial_schema.py"
    spec = importlib.util.spec_from_file_location("_m0001", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.AUDIT_FUNCTION_SQL, [
        "DROP TRIGGER IF EXISTS audit_events_append_only ON audit_events",
        "CREATE TRIGGER audit_events_append_only BEFORE UPDATE OR DELETE ON audit_events "
        "FOR EACH ROW EXECUTE FUNCTION audit_events_block_mutation()",
    ]


@pytest.mark.postgres
def test_postgres_trigger_blocks_update_and_delete(client, operator_headers):  # type: ignore[no-untyped-def]
    flow.create_project(client, operator_headers, "clean_25")
    function_sql, trigger_sql = _audit_trigger_sql()
    with flow.db_session() as db:
        db.execute(text(function_sql))
        for stmt in trigger_sql:
            db.execute(text(stmt))
        db.commit()
        event_id = db.scalar(select(AuditEvent.id).order_by(AuditEvent.id.desc()).limit(1))
        for stmt in (f"UPDATE audit_events SET action = 'x' WHERE id = {event_id}",
                     f"DELETE FROM audit_events WHERE id = {event_id}"):
            with pytest.raises(DBAPIError):
                db.execute(text(stmt))
            db.rollback()
