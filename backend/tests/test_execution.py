from __future__ import annotations

import threading
from datetime import date, timedelta

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from app.domain import executor
from app.errors import AppError
from app.models import (
    MigrationRun,
    RunAttempt,
    SourceRecord,
    TgtCustomer,
    utcnow,
)
from app.security import decode_access_token
from app.services import plans, runs
from app.services.approvals import latest_approval
from tests import flow

_COMPARE = ("legacy_id", "first_name", "last_name", "email", "phone_e164", "signup_date",
            "country_code", "status", "credit_limit_cents", "marketing_opt_in", "account_tier",
            "row_hash")


def _target(project_id: int) -> list[tuple]:
    with flow.db_session() as db:
        rows = db.scalars(select(TgtCustomer).where(TgtCustomer.project_id == project_id)
                          .order_by(TgtCustomer.legacy_id)).all()
        return [tuple(getattr(r, c) for c in _COMPARE) for r in rows]


def test_same_key_replays_and_other_fingerprint_conflicts(client, operator_headers, approver_headers):  # noqa: E501
    _, version = flow.approved_version(client, operator_headers, approver_headers)
    key = flow.new_key()
    first = flow.execute(client, operator_headers, version["id"], key)
    assert first.status_code == 201, first.text
    run = first.json()
    assert run["status"] == "COMPLETED" and run["replayed"] is False
    assert (run["inserted"], run["skipped_existing"], run["quarantined"]) == (45, 0, 0)
    assert run["reconciliation"]["status"] == "PASS"

    again = flow.execute(client, operator_headers, version["id"], key)
    assert again.status_code == 200
    assert again.json()["id"] == run["id"] and again.json()["replayed"] is True

    other = flow.execute(client, approver_headers, version["id"], key)  # role check first
    assert other.status_code == 403
    _, version_b = flow.approved_version(client, operator_headers, approver_headers, "clean_25")
    reused = flow.execute(client, operator_headers, version_b["id"], key)
    assert reused.status_code == 409
    assert reused.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"

    second = flow.execute(client, operator_headers, version["id"])  # new key, run still active
    assert second.status_code == 409 and second.json()["error"]["code"] == "INVALID_STATE"
    assert flow.execute(client, operator_headers, version["id"], "short").status_code == 422


def test_fault_then_retry_equals_clean_run(client, operator_headers, approver_headers):  # type: ignore[no-untyped-def]
    project_a, version_a = flow.approved_version(client, operator_headers, approver_headers)
    res = flow.execute(client, operator_headers, version_a["id"], simulate_failure_after=30)
    assert res.status_code == 201
    failed = res.json()
    assert failed["status"] == "FAILED" and failed["inserted"] == 30
    assert failed["last_error"]["code"] == "FAULT_INJECTED"
    assert failed["reconciliation"]["status"] == "FAIL"
    assert len(_target(project_a["id"])) == 30

    res = client.post(f"/api/runs/{failed['id']}/retry", headers=operator_headers)
    assert res.status_code == 200, res.text
    done = res.json()
    assert done["status"] == "COMPLETED" and done["inserted"] == 45
    assert [(a["kind"], a["status"], a["inserted"]) for a in done["attempts"]] == [
        ("EXECUTE", "FAILED", 30), ("RETRY", "COMPLETED", 15)]
    assert done["reconciliation"]["status"] == "PASS"
    assert client.post(f"/api/runs/{failed['id']}/retry",
                       headers=operator_headers).status_code == 409

    project_b, version_b = flow.approved_version(client, operator_headers, approver_headers)
    assert flow.execute(client, operator_headers, version_b["id"]).json()["inserted"] == 45
    rows_a, rows_b = _target(project_a["id"]), _target(project_b["id"])
    assert rows_a == rows_b and len(rows_a) == 45
    assert len({r[0] for r in rows_a}) == 45  # no duplicates


def test_target_conflicts_are_classified_and_the_run_continues(client, operator_headers, approver_headers):  # noqa: E501
    project, version = flow.approved_version(client, operator_headers, approver_headers)
    pid = project["id"]
    with flow.db_session() as db:
        appr = latest_approval(db, version["id"])
        other = MigrationRun(project_id=pid, plan_version_id=version["id"], approval_id=appr.id,
                             idempotency_key=flow.new_key(), request_fingerprint="x",
                             status="ROLLED_BACK", created_by=appr.actor_id)
        db.add(other)
        db.flush()
        common = dict(project_id=pid, first_name="X", last_name="Y", signup_date=date(2020, 1, 1),
                      country_code="US", status="active", marketing_opt_in=False,
                      account_tier="standard", migration_run_id=other.id, row_hash="0" * 64)
        db.add(TgtCustomer(legacy_id="C1001", email="someone@example.com", **common))
        db.add(TgtCustomer(legacy_id="Z9999", email="ananya.rossi.1002@example.net", **common))
        db.commit()

    res = flow.execute(client, operator_headers, version["id"])
    run = res.json()
    assert res.status_code == 201 and run["status"] == "COMPLETED"
    assert (run["inserted"], run["skipped_existing"], run["quarantined"]) == (43, 1, 1)
    results = client.get(f"/api/runs/{run['id']}/results", params={"outcome": "QUARANTINED"},
                         headers=operator_headers).json()["items"]
    err = results[0]["errors"][0]
    assert results[0]["legacy_id"] == "C1002"
    assert err["code"] == "TARGET_UNIQUE_CONFLICT" and err["stage"] == "execute"
    assert err["existing_legacy_id"] == "Z9999"
    assert run["reconciliation"]["status"] == "PASS"


def test_check_violation_falls_back_to_row_by_row(client, operator_headers, approver_headers, monkeypatch):  # noqa: E501
    project, version = flow.approved_version(client, operator_headers, approver_headers,
                                             "clean_25")
    original = executor.target_row

    def bad_status(project_id, run_id, rec):  # type: ignore[no-untyped-def]
        row = original(project_id, run_id, rec)
        if rec.row_number == 3:
            row["status"] = "bogus"  # violates the target CHECK constraint
        return row

    monkeypatch.setattr(executor, "target_row", bad_status)
    run = flow.execute(client, operator_headers, version["id"]).json()
    assert run["status"] == "COMPLETED"
    assert (run["inserted"], run["quarantined"]) == (24, 1)
    items = client.get(f"/api/runs/{run['id']}/results", params={"outcome": "QUARANTINED"},
                       headers=operator_headers).json()["items"]
    assert items[0]["row_number"] == 3
    assert items[0]["errors"][0]["code"] == "TARGET_CONSTRAINT_VIOLATION"


def test_drift_is_detected(client, operator_headers, approver_headers):  # type: ignore[no-untyped-def]
    project, version = flow.approved_version(client, operator_headers, approver_headers,
                                             "clean_25")
    with flow.db_session() as db:
        rec = db.scalars(select(SourceRecord).where(SourceRecord.project_id == project["id"],
                                                    SourceRecord.row_number == 2)).one()
        db.execute(update(SourceRecord).where(SourceRecord.id == rec.id)
                   .values(payload={**rec.payload, "full_name": "Changed Name"}))
        db.commit()
    res = flow.execute(client, operator_headers, version["id"])
    assert res.status_code == 409
    err = res.json()["error"]
    assert err["code"] == "DRIFT_DETECTED" and err["details"]["row_numbers"] == [2]
    run = client.get(f"/api/runs/{err['details']['run_id']}", headers=operator_headers).json()
    assert run["status"] == "FAILED" and run["inserted"] == 0
    assert run["last_error"]["code"] == "DRIFT_DETECTED"


def test_partial_index_allows_one_active_run(client, operator_headers, approver_headers):  # type: ignore[no-untyped-def]
    project, version = flow.approved_version(client, operator_headers, approver_headers,
                                             "clean_25")
    run = flow.execute(client, operator_headers, version["id"]).json()
    with flow.db_session() as db:
        db.add(MigrationRun(project_id=project["id"], plan_version_id=version["id"],
                            approval_id=run["approval_id"], idempotency_key=flow.new_key(),
                            request_fingerprint="x", status="RUNNING",
                            created_by=run["created_by"]))
        with pytest.raises(IntegrityError):
            db.commit()


def test_stale_running_runs_are_marked_interrupted(client, operator_headers, approver_headers):  # noqa: E501
    _, version = flow.approved_version(client, operator_headers, approver_headers, "clean_25")
    failed = flow.execute(client, operator_headers, version["id"],
                          simulate_failure_after=5).json()
    with flow.db_session() as db:
        old = utcnow() - timedelta(minutes=30)
        db.execute(update(MigrationRun).where(MigrationRun.id == failed["id"])
                   .values(status="RUNNING", updated_at=old))
        db.add(RunAttempt(run_id=failed["id"], attempt_number=2, kind="RETRY", status="RUNNING"))
        db.commit()
        assert runs.recover_stale_runs(db) >= 1
        run = db.get(MigrationRun, failed["id"])
        attempt = db.scalars(select(RunAttempt).where(RunAttempt.run_id == run.id,
                                                      RunAttempt.attempt_number == 2)).one()
        assert run.status == "FAILED" and attempt.error_code == "INTERRUPTED"
    res = client.post(f"/api/runs/{failed['id']}/retry", headers=operator_headers)
    assert res.json()["status"] == "COMPLETED" and res.json()["inserted"] == 25


@pytest.mark.postgres
def test_concurrent_executes_create_one_run(client, operator_headers, approver_headers):  # type: ignore[no-untyped-def]
    project, version = flow.approved_version(client, operator_headers, approver_headers,
                                             "clean_25")
    user = decode_access_token(operator_headers["Authorization"].split(" ", 1)[1])
    outcomes: list[str] = []

    def go() -> None:
        with flow.db_session() as db:
            v = plans.get_version(db, version["id"])
            try:
                runs.execute(db, user, v, flow.new_key(), None)
                outcomes.append("ok")
            except AppError as exc:
                outcomes.append(exc.code)

    threads = [threading.Thread(target=go) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(outcomes) == ["INVALID_STATE", "ok"]
    with flow.db_session() as db:
        count = db.scalar(select(func.count()).select_from(MigrationRun)
                          .where(MigrationRun.project_id == project["id"]))
    assert count == 1
