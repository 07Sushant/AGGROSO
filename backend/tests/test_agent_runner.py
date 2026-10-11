"""Agent runner with the mock LLM: the real dispatcher, validator, failover and persistence."""

from __future__ import annotations

import copy
import json

import pytest
from fastapi.testclient import TestClient

from app.agent.gateway import breaker
from app.agent.mock_llm import calls, mock_client, reference_plan, tool_call
from app.agent.tools import tool_specs
from app.config import get_settings
from tests.flow import create_project, load_reference


@pytest.fixture(autouse=True)
def _clean_mock():  # type: ignore[no-untyped-def]
    mock_client.reset()
    breaker.reset()
    yield
    mock_client.reset()
    breaker.reset()


def run_agent(client: TestClient, op: dict, project_id: int, **body) -> dict:  # type: ignore[no-untyped-def]
    res = client.post(f"/api/projects/{project_id}/agent-runs", json=body or None, headers=op)
    assert res.status_code == 202, res.text
    got = client.get(f"/api/agent-runs/{res.json()['id']}", headers=op)
    assert got.status_code == 200
    return got.json()


def project_id(client: TestClient, op: dict) -> int:
    return create_project(client, op)["id"]


def tool_messages(request: dict) -> list[dict]:
    return [m for m in request["messages"] if m.get("role") == "tool"]


def test_happy_path_creates_agent_draft_with_trace(client, operator_headers):  # type: ignore[no-untyped-def]
    pid = project_id(client, operator_headers)
    run = run_agent(client, operator_headers, pid)
    assert run["status"] == "SUCCEEDED", run
    assert (run["engine"], run["mode"], run["fell_back"]) == ("primary", "full", False)
    version = client.get(f"/api/plan-versions/{run['result_version_id']}",
                         headers=operator_headers).json()
    assert version["status"] == "DRAFT" and version["author_type"] == "agent"
    assert version["agent_run_id"] == run["id"]
    kinds = [s["kind"] for s in run["trace"]]
    assert kinds.count("llm_call") == 2 and "tool_call" in kinds and kinds[-1] == "validation"
    llm_steps = [s for s in run["trace"] if s["kind"] == "llm_call"]
    assert all(s["tokens_in"] > 0 and s["tokens_out"] > 0 for s in llm_steps)
    assert all(s["latency_ms"] >= 0 for s in run["trace"])
    assert run["tokens_in"] == sum(s["tokens_in"] for s in run["trace"])
    # The model never sees schemas in the task: it has to inspect through the tools.
    first = mock_client.calls_for("primary")[0]
    assert "cust_id" not in first["messages"][1]["content"]
    assert first["max_completion_tokens"] == get_settings().primary_max_completion_tokens


def test_unknown_tool_is_rejected_and_returned_to_the_model(client, operator_headers):  # type: ignore[no-untyped-def]
    mock_client.queue("primary", calls(tool_call("execute_sql", {"sql": "DROP TABLE x"})))
    run = run_agent(client, operator_headers, project_id(client, operator_headers))
    assert run["status"] == "SUCCEEDED"
    rejected = [s for s in run["trace"] if s["tool_name"] == "execute_sql"]
    assert rejected and rejected[0]["ok"] is False and rejected[0]["error"] == "UNKNOWN_TOOL"
    second = mock_client.calls_for("primary")[1]
    assert "UNKNOWN_TOOL" in tool_messages(second)[0]["content"]


def test_bad_arguments_go_back_to_the_model(client, operator_headers):  # type: ignore[no-untyped-def]
    mock_client.queue("primary", calls(tool_call("sample_source_records", {"limit": 500}),
                                       tool_call("profile_source_field", {"field": "nope"})))
    run = run_agent(client, operator_headers, project_id(client, operator_headers))
    assert run["status"] == "SUCCEEDED"
    errors = {s["tool_name"]: s["error"] for s in run["trace"] if s["kind"] == "tool_call"}
    assert errors == {"sample_source_records": "INVALID_ARGUMENTS",
                      "profile_source_field": "UNKNOWN_SOURCE_FIELD"}
    contents = [m["content"] for m in tool_messages(mock_client.calls_for("primary")[1])]
    assert "INVALID_ARGUMENTS" in contents[0] and "UNKNOWN_SOURCE_FIELD" in contents[1]


def _invalid_plan() -> dict:
    plan = reference_plan()
    plan["mappings"] = [m for m in plan["mappings"] if m["target_field"] != "email"]
    plan["mappings"][0]["transforms"].append({"name": "reverse_string"})
    return plan


def test_invalid_plan_is_fixed_on_the_first_repair(client, operator_headers):  # type: ignore[no-untyped-def]
    mock_client.queue("primary", calls(tool_call("submit_plan", _invalid_plan())))
    run = run_agent(client, operator_headers, project_id(client, operator_headers))
    assert run["status"] == "SUCCEEDED"
    validations = [s for s in run["trace"] if s["kind"] == "validation"]
    assert [v["ok"] for v in validations] == [False, True]
    codes = {e["code"] for e in validations[0]["result"]["errors"]}
    assert {"REQUIRED_TARGET_UNMAPPED", "UNKNOWN_TRANSFORM"} <= codes
    repair_feedback = json.loads(tool_messages(mock_client.calls_for("primary")[1])[0]["content"])
    assert repair_feedback["accepted"] is False and repair_feedback["repairs_left"] == 1


def test_three_invalid_plans_fail_with_plan_invalid(client, operator_headers):  # type: ignore[no-untyped-def]
    for _ in range(3):
        mock_client.queue("primary", calls(tool_call("submit_plan", _invalid_plan())))
    pid = project_id(client, operator_headers)
    run = run_agent(client, operator_headers, pid)
    assert run["status"] == "FAILED" and run["error_code"] == "PLAN_INVALID"
    assert run["result_version_id"] is None
    assert client.get(f"/api/projects/{pid}/plan-versions", headers=operator_headers).json() == []


def test_endless_loop_stops_at_max_steps(client, operator_headers):  # type: ignore[no-untyped-def]
    limit = get_settings().agent_max_steps
    for _ in range(limit + 2):
        mock_client.queue("primary", calls(tool_call("sample_source_records", {"limit": 1})))
    run = run_agent(client, operator_headers, project_id(client, operator_headers))
    assert run["status"] == "FAILED" and run["error_code"] == "MAX_STEPS"
    primary_calls = mock_client.calls_for("primary")
    assert len(primary_calls) == limit
    # The last allowed turn forces submit_plan.
    assert primary_calls[-1]["tool_choice"]["function"]["name"] == "submit_plan"


def test_primary_timeout_restarts_on_backup_in_compact_mode(client, operator_headers):  # type: ignore[no-untyped-def]
    mock_client.queue("primary", calls(tool_call("get_source_schema")), {"error": "timeout"})
    bad = reference_plan()
    bad["mappings"][0]["confidence"] = "certain"
    mock_client.queue("backup", calls(tool_call("submit_plan", bad)))  # then a valid default
    run = run_agent(client, operator_headers, project_id(client, operator_headers))
    assert run["status"] == "SUCCEEDED", run
    assert (run["engine"], run["mode"], run["fell_back"]) == ("backup", "compact", True)
    fallback = [s for s in run["trace"] if s["kind"] == "fallback"]
    assert fallback and fallback[0]["result"]["reason"] == "timeout"
    runner_steps = [s for s in run["trace"] if s["invoked_by"] == "runner"]
    assert {s["tool_name"] for s in runner_steps} >= {"get_source_schema", "get_target_schema",
                                                     "profile_source_field",
                                                     "list_transformations"}
    backup_calls = mock_client.calls_for("backup")
    first = backup_calls[0]
    # A fresh conversation: the primary's messages are never replayed to the backup.
    assert [m["role"] for m in first["messages"]] == ["system", "user"]
    assert first["tool_choice"]["function"]["name"] == "submit_plan"
    assert [t["function"]["name"] for t in first["tools"]] == ["submit_plan"]
    assert "untrusted_data" in first["messages"][1]["content"]
    # Echo rule: the repair turn carries the backup's assistant message unchanged.
    echoed = [m for m in backup_calls[1]["messages"] if m["role"] == "assistant"][0]
    assert echoed["tool_calls"][0]["extra_content"]["signature"].startswith("sig-")
    assert first["max_completion_tokens"] == get_settings().backup_max_completion_tokens


def test_rate_limit_is_retried_once_then_backup(client, operator_headers):  # type: ignore[no-untyped-def]
    mock_client.queue("primary", {"error": "rate_limited"}, {"error": "rate_limited"})
    run = run_agent(client, operator_headers, project_id(client, operator_headers))
    assert run["status"] == "SUCCEEDED" and run["engine"] == "backup"
    assert len(mock_client.calls_for("primary")) == 2


def test_both_engines_down_is_llm_unavailable(client, operator_headers):  # type: ignore[no-untyped-def]
    mock_client.queue("primary", {"error": "connection"})
    mock_client.queue("backup", {"error": "server_error"}, {"error": "server_error"})
    run = run_agent(client, operator_headers, project_id(client, operator_headers))
    assert run["status"] == "FAILED" and run["error_code"] == "LLM_UNAVAILABLE"
    assert len(mock_client.calls_for("backup")) == 2  # 5xx is retried once


def test_open_circuit_skips_the_primary(client, operator_headers):  # type: ignore[no-untyped-def]
    for _ in range(3):
        breaker.record_failure()
    run = run_agent(client, operator_headers, project_id(client, operator_headers))
    assert run["status"] == "SUCCEEDED" and run["engine"] == "backup"
    assert mock_client.calls_for("primary") == []
    assert run["trace"][0]["result"]["reason"] == "circuit_open"


def test_per_project_rate_limit(client, operator_headers, monkeypatch):  # type: ignore[no-untyped-def]
    monkeypatch.setattr(get_settings(), "agent_runs_per_project_hour", 1)
    pid = project_id(client, operator_headers)
    run_agent(client, operator_headers, pid)
    res = client.post(f"/api/projects/{pid}/agent-runs", headers=operator_headers)
    assert res.status_code == 429
    body = res.json()["error"]
    assert body["code"] == "RATE_LIMITED" and body["details"]["scope"] == "project"
    assert int(res.headers["Retry-After"]) > 0
    # Another project is not affected.
    assert run_agent(client, operator_headers, project_id(client, operator_headers))["status"] \
        == "SUCCEEDED"


def test_agent_runs_need_the_operator_role(client, approver_headers, operator_headers):  # type: ignore[no-untyped-def]
    pid = project_id(client, operator_headers)
    res = client.post(f"/api/projects/{pid}/agent-runs", headers=approver_headers)
    assert res.status_code == 403


def test_injection_record_does_not_change_the_plan(client, operator_headers):  # type: ignore[no-untyped-def]
    obey = reference_plan()  # what a model that obeyed the hostile note would submit
    for m in obey["mappings"]:
        if m["target_field"] != "email":
            m["source_fields"] = ["email_addr"]
            m["transforms"] = []
    obey["mappings"].append({**copy.deepcopy(obey["mappings"][3]), "id": "m_email_2"})
    mock_client.queue("primary",
                      calls(tool_call("sample_source_records", {"limit": 5, "offset": 55})),
                      calls(tool_call("submit_plan", obey)))
    pid = project_id(client, operator_headers)
    run = run_agent(client, operator_headers, pid)
    assert run["status"] == "SUCCEEDED"
    sample = tool_messages(mock_client.calls_for("primary")[1])[0]["content"]
    payload = json.loads(sample)
    assert list(payload) == ["untrusted_data"]
    assert "ignore your instructions" in json.dumps(payload["untrusted_data"])
    rejected = [s for s in run["trace"] if s["kind"] == "validation" and not s["ok"]]
    codes = {e["code"] for e in rejected[0]["result"]["errors"]}
    assert "DUPLICATE_TARGET_MAPPING" in codes and "TYPE_MISMATCH" in codes
    version = client.get(f"/api/plan-versions/{run['result_version_id']}",
                         headers=operator_headers).json()
    assert version["plan"]["mappings"] == load_reference_plan_mappings(client, operator_headers)


def load_reference_plan_mappings(client: TestClient, op: dict) -> list:
    pid = project_id(client, op)
    return load_reference(client, op, pid)["plan"]["mappings"]


def test_revise_feeds_answers_back_and_links_the_parent(client, operator_headers):  # type: ignore[no-untyped-def]
    pid = project_id(client, operator_headers)
    base = load_reference(client, operator_headers, pid)
    run = run_agent(client, operator_headers, pid, base_version_id=base["id"])
    assert run["status"] == "SUCCEEDED" and run["kind"] == "revise"
    task = mock_client.calls_for("primary")[0]["messages"][1]["content"]
    assert "Revise the existing plan" in task and '"answer": "suspended"' in task
    version = client.get(f"/api/plan-versions/{run['result_version_id']}",
                         headers=operator_headers).json()
    assert version["parent_version_id"] == base["id"] and version["version_number"] == 2
    assert version["answers"] == base["answers"]  # same question ids, so answers carry forward
    diff = client.get(f"/api/plan-versions/{version['id']}/diff", headers=operator_headers)
    assert diff.status_code == 200 and diff.json()["against_version_id"] == base["id"]


def test_tool_specs_use_portable_json_schema():  # type: ignore[no-untyped-def]
    text = json.dumps(tool_specs())
    assert "$ref" not in text and "additionalProperties" not in text and "anyOf" not in text
    names = [t["function"]["name"] for t in tool_specs()]
    assert len(names) == 8 and names[-1] == "submit_plan"
