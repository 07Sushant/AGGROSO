from __future__ import annotations

import csv
import io
import json
from datetime import date
from pathlib import Path

from sqlalchemy import func, select

from app.domain.dry_run import SourceRow, compute_dry_run
from app.models import DryRun, DryRunRecord, MigrationRun, TgtCustomer
from app.services import inputs
from tests import flow

EXPECTED = json.loads((Path(__file__).parent / "expected_counts.json").read_text())


def _rows(key: str) -> list[SourceRow]:
    return [SourceRow(i + 1, i + 1, r) for i, r in enumerate(inputs.dataset(key)["records"])]


def test_baseline_counts_codes_and_invariants():
    exp = EXPECTED["baseline_60"]
    result = compute_dry_run(_rows("baseline_60"), inputs.reference_plan()["plan"])
    assert (result.source_count, result.transformed_count, result.accepted_count,
            result.rejected_count) == (exp["source"], exp["transformed"], exp["accepted"],
                                       exp["rejected"])
    assert result.rejected_by_code() == exp["rejected_by_code"]
    got = {str(r.row_number): r.errors[0]["code"] for r in result.records
           if r.outcome == "REJECTED"}
    assert got == exp["rejected_rows"]
    assert result.source_count == result.accepted_count + result.rejected_count
    assert result.accepted_count <= result.transformed_count <= result.source_count
    hostile = next(r for r in result.records if r.row_number == exp["hostile_row"])
    assert hostile.outcome == "ACCEPTED" and "notes" not in hostile.transformed
    clean = compute_dry_run(_rows("clean_25"), inputs.reference_plan()["plan"])
    assert clean.rejected_count == 0 and clean.accepted_count == 25


def test_same_hash_over_three_runs_and_rows_order_independent():
    plan = inputs.reference_plan()["plan"]
    rows = _rows("baseline_60")
    hashes = {compute_dry_run(rows, plan).result_hash for _ in range(3)}
    hashes.add(compute_dry_run(list(reversed(rows)), plan).result_hash)
    assert len(hashes) == 1


def test_stored_dry_run_never_touches_target(client, operator_headers, approver_headers):  # type: ignore[no-untyped-def]
    project, version = flow.approved_version(client, operator_headers, approver_headers)
    first = flow.dry_run(client, operator_headers, version["id"])
    assert first["counts"] == {"source": 60, "transformed": 55, "accepted": 45, "rejected": 15}
    assert flow.execute(client, operator_headers, version["id"]).status_code == 201
    with flow.db_session() as db:
        target_before = db.scalar(select(func.count()).select_from(TgtCustomer)
                                  .where(TgtCustomer.project_id == project["id"]))
        db.add(TgtCustomer(  # a rogue target row must not influence the dry run
            project_id=project["id"], legacy_id="ROGUE", first_name="R", last_name="R",
            email="rogue@example.com", signup_date=date(2020, 1, 1), country_code="US",
            status="active", marketing_opt_in=False, account_tier="standard",
            migration_run_id=db.scalar(select(MigrationRun.id)
                                       .where(MigrationRun.project_id == project["id"])),
            row_hash="x" * 64,
        ))
        db.commit()
    second = flow.dry_run(client, operator_headers, version["id"])
    assert second["result_hash"] == first["result_hash"]
    with flow.db_session() as db:
        target_after = db.scalar(select(func.count()).select_from(TgtCustomer)
                                 .where(TgtCustomer.project_id == project["id"]))
    assert target_after == target_before + 1  # only the rogue row; dry runs wrote nothing


def test_determinism_check_stores_nothing(client, operator_headers):  # type: ignore[no-untyped-def]
    project = flow.create_project(client, operator_headers)
    version = flow.load_reference(client, operator_headers, project["id"])
    dry = flow.dry_run(client, operator_headers, version["id"])
    with flow.db_session() as db:
        before = (db.scalar(select(func.count()).select_from(DryRun)),
                  db.scalar(select(func.count()).select_from(DryRunRecord)))
    res = client.post(f"/api/plan-versions/{version['id']}/determinism", headers=operator_headers)
    body = res.json()
    assert body["deterministic"] is True and body["matches_latest_dry_run"] is True
    assert len(set(body["hashes"])) == 1 and body["hashes"][0] == dry["result_hash"]
    with flow.db_session() as db:
        after = (db.scalar(select(func.count()).select_from(DryRun)),
                 db.scalar(select(func.count()).select_from(DryRunRecord)))
    assert before == after


def test_quarantine_records_filter_and_export(client, operator_headers):  # type: ignore[no-untyped-def]
    project = flow.create_project(client, operator_headers)
    version = flow.load_reference(client, operator_headers, project["id"])
    dry = flow.dry_run(client, operator_headers, version["id"])
    res = client.get(f"/api/dry-runs/{dry['id']}/records",
                     params={"outcome": "REJECTED", "code": "PARSE_DATE_FAILED"},
                     headers=operator_headers).json()
    assert res["total"] == 2
    err = res["items"][0]["errors"][0]
    assert err["stage"] == "transform" and err["transform"] == "parse_date"
    assert err["target_field"] == "signup_date" and err["source_fields"] == ["signup_dt"]

    csv_res = client.get(f"/api/dry-runs/{dry['id']}/export", params={"format": "csv"},
                         headers=operator_headers)
    assert csv_res.headers["content-type"].startswith("text/csv")
    assert "attachment" in csv_res.headers["content-disposition"]
    rows = list(csv.DictReader(io.StringIO(csv_res.text)))
    assert len(rows) == 15 and {r["code"] for r in rows} >= {"RANGE", "DUPLICATE_EMAIL"}
    json_rows = client.get(f"/api/dry-runs/{dry['id']}/export", params={"format": "json"},
                           headers=operator_headers).json()
    assert len(json_rows) == 15
