from __future__ import annotations

import copy

from sqlalchemy import select, update

from app.models import Approval, PlanVersion
from tests import flow


def _err(res):  # type: ignore[no-untyped-def]
    return res.json()["error"]


def test_gate_blocks_until_checklist_is_complete(client, operator_headers, approver_headers):  # type: ignore[no-untyped-def]
    op, ap = operator_headers, approver_headers
    project = flow.create_project(client, op)
    version = flow.load_reference(client, op, project["id"])
    vid = version["id"]

    # Executing a DRAFT -> 403
    res = flow.execute(client, op, vid)
    assert res.status_code == 403 and _err(res)["code"] == "APPROVAL_REQUIRED"

    # No dry run -> 409 (the unacknowledged high risk is reported too)
    res = client.post(f"/api/plan-versions/{vid}/approve", json={}, headers=ap)
    assert res.status_code == 409
    details = _err(res)["details"]
    assert "dry_run" in details["blockers"] and "high_risks" in details["blockers"]
    assert details["unacknowledged_high_risk_ids"] == ["r_email_dupes"]

    flow.dry_run(client, op, vid)
    res = client.post(f"/api/plan-versions/{vid}/approve", json={}, headers=ap)
    assert res.status_code == 409 and _err(res)["details"]["blockers"] == ["high_risks"]

    # A new version with an unanswered question -> 409 listing the question id
    plan = copy.deepcopy(version["plan"])
    plan["clarification_questions"].append(
        {"id": "Q9", "question": "Anything else?", "related_fields": [], "options": []})
    v2 = client.post(f"/api/projects/{project['id']}/plan-versions",
                     json={"plan": plan, "change_note": "extra question"}, headers=op).json()
    flow.ack_high_risks(client, op, v2)
    flow.dry_run(client, op, v2["id"])
    res = client.post(f"/api/plan-versions/{v2['id']}/approve", json={}, headers=ap)
    assert res.status_code == 409
    assert _err(res)["details"]["unanswered_question_ids"] == ["Q9"]

    checklist = client.get(f"/api/plan-versions/{vid}/approval-checklist", headers=ap).json()
    assert checklist["can_approve"] is False and checklist["blockers"] == ["high_risks"]
    flow.ack_high_risks(client, op, version)
    checklist = client.get(f"/api/plan-versions/{vid}/approval-checklist", headers=ap).json()
    assert checklist["can_approve"] is True and checklist["self_approval"] is False
    body = flow.approve(client, ap, vid)
    assert body["version"]["status"] == "APPROVED"
    assert body["approval"]["self_approved"] is False
    assert body["approval"]["dry_run_result_hash"] == checklist["dry_run"]["result_hash"]


def test_roles_are_enforced(client, operator_headers, approver_headers):  # type: ignore[no-untyped-def]
    op, ap = operator_headers, approver_headers
    project = flow.create_project(client, op, "clean_25")
    version = flow.ack_high_risks(client, op, flow.load_reference(client, op, project["id"]))
    flow.dry_run(client, op, version["id"])
    res = client.post(f"/api/plan-versions/{version['id']}/approve", json={}, headers=op)
    assert res.status_code == 403 and _err(res)["code"] == "FORBIDDEN"
    flow.approve(client, ap, version["id"])
    res = flow.execute(client, ap, version["id"])
    assert res.status_code == 403 and _err(res)["code"] == "FORBIDDEN"


def test_self_approval_is_allowed_and_flagged(client, operator_headers, approver_headers):  # type: ignore[no-untyped-def]
    op, ap = operator_headers, approver_headers
    project = flow.create_project(client, op, "clean_25")
    ref = flow.load_reference(client, op, project["id"])
    plan = copy.deepcopy(ref["plan"])
    plan["risk_summary"] = "Edited by the approver."
    res = client.post(f"/api/projects/{project['id']}/plan-versions",
                      json={"plan": plan, "change_note": "approver edit"}, headers=ap)
    assert res.status_code == 201, res.text
    v2 = flow.ack_high_risks(client, ap, res.json())
    flow.dry_run(client, op, v2["id"])
    checklist = client.get(f"/api/plan-versions/{v2['id']}/approval-checklist", headers=ap).json()
    item = next(i for i in checklist["items"] if i["id"] == "separation_of_duties")
    assert checklist["can_approve"] is True and checklist["self_approval"] is True
    assert item["ok"] is False and item["blocking"] is False
    assert item["detail"] == "Self-approval: you edited this version."
    body = flow.approve(client, ap, v2["id"])
    assert body["approval"]["self_approved"] is True
    history = client.get(f"/api/projects/{project['id']}/history", headers=op).json()
    event = next(e for e in history["events"] if e["action"] == "plan.approved")
    assert event["details"]["self_approved"] is True


def test_tampered_plan_and_revoke_block_execution(client, operator_headers, approver_headers):  # type: ignore[no-untyped-def]
    op, ap = operator_headers, approver_headers
    _, version = flow.approved_version(client, op, ap, "clean_25")
    vid = version["id"]

    with flow.db_session() as db:
        original = db.scalar(select(PlanVersion.plan).where(PlanVersion.id == vid))
        tampered = copy.deepcopy(original)
        tampered["mappings"][0]["transforms"] = []
        db.execute(update(PlanVersion).where(PlanVersion.id == vid).values(plan=tampered))
        db.commit()
    res = flow.execute(client, op, vid)
    assert res.status_code == 403 and _err(res)["code"] == "APPROVAL_REQUIRED"
    with flow.db_session() as db:
        db.execute(update(PlanVersion).where(PlanVersion.id == vid).values(plan=original))
        db.commit()

    res = client.post(f"/api/plan-versions/{vid}/revoke", json={"comment": "not yet"},
                      headers=ap)
    assert res.status_code == 200 and res.json()["version"]["status"] == "DRAFT"
    res = flow.execute(client, op, vid)
    assert res.status_code == 403 and _err(res)["code"] == "APPROVAL_REQUIRED"
    with flow.db_session() as db:
        decisions = db.scalars(select(Approval.decision).where(Approval.plan_version_id == vid)
                               .order_by(Approval.id)).all()
    assert decisions == ["APPROVED", "REVOKED"]

    # Re-approve, run, then revoke is refused while the run is active.
    flow.approve(client, ap, vid)
    assert flow.execute(client, op, vid).status_code == 201
    res = client.post(f"/api/plan-versions/{vid}/revoke", json={"comment": "x"}, headers=ap)
    assert res.status_code == 409


def test_reject_and_supersede(client, operator_headers, approver_headers):  # type: ignore[no-untyped-def]
    op, ap = operator_headers, approver_headers
    project, v1 = flow.approved_version(client, op, ap, "clean_25")
    v2 = flow.ack_high_risks(client, op, flow.load_reference(client, op, project["id"]))
    flow.dry_run(client, op, v2["id"])
    flow.approve(client, ap, v2["id"])
    assert client.get(f"/api/plan-versions/{v1['id']}", headers=op).json()["status"] == \
        "SUPERSEDED"
    v3 = flow.load_reference(client, op, project["id"])
    res = client.post(f"/api/plan-versions/{v3['id']}/reject", json={"comment": "no"}, headers=ap)
    assert res.status_code == 200 and res.json()["version"]["status"] == "REJECTED"
    res = client.post(f"/api/plan-versions/{v3['id']}/reject", json={"comment": "no"}, headers=ap)
    assert res.status_code == 409 and _err(res)["code"] == "INVALID_STATE"
