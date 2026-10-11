from __future__ import annotations

from sqlalchemy import func, select

from app.models import Rollback, TgtCustomer
from tests import flow


def _target_count(project_id: int, run_id: int | None = None) -> int:
    with flow.db_session() as db:
        stmt = select(func.count()).select_from(TgtCustomer).where(
            TgtCustomer.project_id == project_id)
        if run_id is not None:
            stmt = stmt.where(TgtCustomer.migration_run_id == run_id)
        return db.scalar(stmt) or 0


def test_rollback_deletes_only_this_run_and_replay_does_not_reinsert(client, operator_headers, approver_headers):  # noqa: E501
    op, ap = operator_headers, approver_headers
    project, version = flow.approved_version(client, op, ap)
    other_project, other_version = flow.approved_version(client, op, ap, "clean_25")
    other_run = flow.execute(client, op, other_version["id"]).json()
    key = flow.new_key()
    run = flow.execute(client, op, version["id"], key).json()
    assert _target_count(project["id"], run["id"]) == 45

    res = client.post(f"/api/runs/{run['id']}/rollback", json={"reason": "demo"}, headers=op)
    assert res.status_code == 403  # approver only
    res = client.post(f"/api/runs/{run['id']}/rollback", json={"reason": ""}, headers=ap)
    assert res.status_code == 422  # a reason is required

    res = client.post(f"/api/runs/{run['id']}/rollback", json={"reason": "demo rollback"},
                      headers=ap)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "ROLLED_BACK" and body["rollback"]["deleted_count"] == 45
    assert body["reconciliation"]["status"] == "PASS"
    assert body["reconciliation"]["totals"]["target_rows"] == 0
    assert _target_count(project["id"]) == 0
    assert _target_count(other_project["id"], other_run["id"]) == 25  # untouched

    again = client.post(f"/api/runs/{run['id']}/rollback", json={"reason": "again"}, headers=ap)
    assert again.status_code == 409 and again.json()["error"]["code"] == "INVALID_STATE"

    replay = flow.execute(client, op, version["id"], key)
    assert replay.status_code == 200 and replay.json()["replayed"] is True
    assert replay.json()["status"] == "ROLLED_BACK"
    assert _target_count(project["id"]) == 0

    fresh = flow.execute(client, op, version["id"])  # a new key may run again
    assert fresh.status_code == 201 and fresh.json()["inserted"] == 45
    with flow.db_session() as db:
        assert db.scalar(select(func.count()).select_from(Rollback)
                         .where(Rollback.run_id == run["id"])) == 1


def test_failed_run_can_be_rolled_back(client, operator_headers, approver_headers):  # type: ignore[no-untyped-def]
    project, version = flow.approved_version(client, operator_headers, approver_headers,
                                             "clean_25")
    run = flow.execute(client, operator_headers, version["id"], simulate_failure_after=10).json()
    assert run["status"] == "FAILED" and _target_count(project["id"]) == 10
    res = client.post(f"/api/runs/{run['id']}/rollback", json={"reason": "abort"},
                      headers=approver_headers)
    assert res.json()["status"] == "ROLLED_BACK" and _target_count(project["id"]) == 0
    assert res.json()["reconciliation"]["status"] == "PASS"
    retry = client.post(f"/api/runs/{run['id']}/retry", headers=operator_headers)
    assert retry.status_code == 409
