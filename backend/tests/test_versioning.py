from __future__ import annotations

import copy

from app.domain.hashing import plan_hash
from tests import flow


def test_new_version_links_parent_and_leaves_old_unchanged(client, operator_headers):  # type: ignore[no-untyped-def]
    project = flow.create_project(client, operator_headers)
    v1 = flow.load_reference(client, operator_headers, project["id"])
    assert v1["version_number"] == 1 and v1["author_type"] == "human"
    assert v1["answers"]["Q1"] == "quarantine" and v1["unanswered_question_ids"] == []
    assert v1["content_hash"] == plan_hash(v1["plan"])

    plan = copy.deepcopy(v1["plan"])
    phone = next(m for m in plan["mappings"] if m["target_field"] == "phone_e164")
    phone["transforms"][1]["params"]["default_country"] = "GB"
    plan["clarification_questions"] = [q for q in plan["clarification_questions"]
                                       if q["id"] != "Q5"]
    plan["clarification_questions"].append(
        {"id": "Q6", "question": "New question?", "related_fields": [], "options": []})
    res = client.post(f"/api/projects/{project['id']}/plan-versions",
                      json={"plan": plan, "change_note": "Assume GB phones"},
                      headers=operator_headers)
    assert res.status_code == 201, res.text
    v2 = res.json()
    assert v2["version_number"] == 2 and v2["parent_version_id"] == v1["id"]
    assert v2["content_hash"] != v1["content_hash"]
    # Answers carry forward only for question ids that still exist.
    assert set(v2["answers"]) == {"Q1", "Q2", "Q3", "Q4"}
    assert v2["unanswered_question_ids"] == ["Q6"]

    old = client.get(f"/api/plan-versions/{v1['id']}", headers=operator_headers).json()
    assert old["plan"] == v1["plan"] and old["content_hash"] == v1["content_hash"]
    assert old["status"] == "DRAFT"

    diff = client.get(f"/api/plan-versions/{v2['id']}/diff", headers=operator_headers).json()
    assert diff["against_version_id"] == v1["id"]
    assert diff["summary"]["changed"] == 1 and diff["summary"]["added"] == 0
    change = diff["mappings"][0]
    assert change["target_field"] == "phone_e164" and "transforms" in change["fields"]
    assert "clarification_questions" in diff["sections"]

    versions = client.get(f"/api/projects/{project['id']}/plan-versions",
                          headers=operator_headers).json()
    assert [v["version_number"] for v in versions] == [2, 1]


def test_hash_is_stable_and_invalid_plans_are_refused(client, operator_headers):  # type: ignore[no-untyped-def]
    project = flow.create_project(client, operator_headers, "clean_25")
    v1 = flow.load_reference(client, operator_headers, project["id"])
    v2 = flow.load_reference(client, operator_headers, project["id"])
    assert v1["content_hash"] == v2["content_hash"]

    bad = copy.deepcopy(v1["plan"])
    bad["mappings"][0]["source_fields"] = ["made_up"]
    res = client.post(f"/api/projects/{project['id']}/plan-versions",
                      json={"plan": bad, "change_note": "x"}, headers=operator_headers)
    assert res.status_code == 422
    assert res.json()["error"]["details"]["errors"][0]["code"] == "UNKNOWN_SOURCE_FIELD"
    check = client.post(f"/api/plan-versions/{v1['id']}/validate", json={"plan": bad},
                        headers=operator_headers).json()
    assert check["valid"] is False


def test_answers_and_risk_acks_validate_ids(client, operator_headers):  # type: ignore[no-untyped-def]
    project = flow.create_project(client, operator_headers, "clean_25")
    v1 = flow.load_reference(client, operator_headers, project["id"])
    res = client.post(f"/api/plan-versions/{v1['id']}/answers",
                      json={"answers": {"Q404": "x"}}, headers=operator_headers)
    assert res.status_code == 422
    res = client.post(f"/api/plan-versions/{v1['id']}/answers",
                      json={"answers": {"Q1": "use '-' placeholder"}}, headers=operator_headers)
    assert res.json()["answers"]["Q1"] == "use '-' placeholder"
    res = client.post(f"/api/plan-versions/{v1['id']}/risk-acks",
                      json={"risk_ids": ["nope"]}, headers=operator_headers)
    assert res.status_code == 422
    acked = flow.ack_high_risks(client, operator_headers, v1)
    assert acked["risk_acks"] == ["r_email_dupes"] and acked["unacknowledged_high_risk_ids"] == []
