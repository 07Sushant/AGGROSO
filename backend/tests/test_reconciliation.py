from __future__ import annotations

from datetime import date

from sqlalchemy import delete, func, select, update

from app.models import DryRun, DryRunRecord, TgtCustomer
from tests import flow


def _completed_run(client, op, ap):  # type: ignore[no-untyped-def]
    project, version = flow.approved_version(client, op, ap, "clean_25")
    run = flow.execute(client, op, version["id"]).json()
    assert run["status"] == "COMPLETED"
    return project, run


def _reconcile(client, headers, run_id):  # type: ignore[no-untyped-def]
    res = client.get(f"/api/runs/{run_id}/reconciliation", headers=headers)
    assert res.status_code == 200
    return res.json()


def _codes(result) -> set[str]:  # type: ignore[no-untyped-def]
    return {d["code"] for d in result["discrepancies"]}


def test_clean_run_passes_and_reconcile_creates_no_dry_runs(client, operator_headers, approver_headers):  # noqa: E501
    _, run = _completed_run(client, operator_headers, approver_headers)
    with flow.db_session() as db:
        before = (db.scalar(select(func.count()).select_from(DryRun)),
                  db.scalar(select(func.count()).select_from(DryRunRecord)))
    result = _reconcile(client, operator_headers, run["id"])
    assert result["status"] == "PASS" and result["discrepancies"] == []
    t = result["totals"]
    assert (t["source"], t["accepted"], t["inserted"], t["target_rows"]) == (25, 25, 25, 25)
    assert all(i["ok"] for i in result["invariants"])
    with flow.db_session() as db:
        after = (db.scalar(select(func.count()).select_from(DryRun)),
                 db.scalar(select(func.count()).select_from(DryRunRecord)))
    assert before == after


def test_deleted_rogue_and_edited_rows_fail(client, operator_headers, approver_headers):  # type: ignore[no-untyped-def]
    project, run = _completed_run(client, operator_headers, approver_headers)
    pid = project["id"]
    with flow.db_session() as db:
        keys = db.scalars(select(TgtCustomer.legacy_id).where(TgtCustomer.project_id == pid)
                          .order_by(TgtCustomer.legacy_id)).all()
        db.execute(delete(TgtCustomer).where(TgtCustomer.project_id == pid,
                                             TgtCustomer.legacy_id == keys[0]))
        db.commit()
    result = _reconcile(client, operator_headers, run["id"])
    assert result["status"] == "FAIL" and result["missing_in_target"] == [keys[0]]
    assert "MISSING_IN_TARGET" in _codes(result)

    with flow.db_session() as db:
        db.add(TgtCustomer(project_id=pid, legacy_id="ROGUE1", first_name="R", last_name="R",
                           email="rogue1@example.com", signup_date=date(2020, 1, 1),
                           country_code="US", status="active", marketing_opt_in=False,
                           account_tier="standard", migration_run_id=run["id"],
                           row_hash="0" * 64))
        db.execute(update(TgtCustomer).where(TgtCustomer.project_id == pid,
                                             TgtCustomer.legacy_id == keys[1])
                   .values(first_name="Edited"))
        db.commit()
    result = _reconcile(client, operator_headers, run["id"])
    assert result["unexpected_in_target"] == ["ROGUE1"]
    assert {"UNEXPECTED_IN_TARGET", "VALUE_MISMATCH", "MISSING_IN_TARGET"} <= _codes(result)
    mismatch = result["value_mismatches"][0]
    assert mismatch["legacy_id"] == keys[1] and mismatch["field"] == "first_name"
    assert mismatch["actual"] == "Edited" and result["value_mismatch_rows"] == 1
