"""The UI vocabulary is primary / backup / mock. No provider or model name may leak."""

from __future__ import annotations

import re

from fastapi.testclient import TestClient

from app.agent import probe
from app.api import routes_health
from app.config import Settings
from app.logging import get_logger

LEAK = re.compile(r"groq|gemini|qwen|google", re.I)


def test_mock_health_and_config_are_alias_only(client: TestClient):
    for path in ("/api/health", "/api/config", "/api/health/live"):
        res = client.get(path)
        assert res.status_code == 200
        assert not LEAK.search(res.text), path
    assert client.get("/api/health").json()["ai"]["status"] == "mock"


def test_live_health_reports_alias_status_without_names(client: TestClient, monkeypatch):  # type: ignore[no-untyped-def]
    live = Settings(llm_mode="live", groq_api_key="k1", gemini_api_key="k2",
                    database_url="sqlite://")

    def fake_probe(engine, _timeout):  # type: ignore[no-untyped-def]
        # The primary "fails" with an error that names the vendor; it must not surface.
        get_logger("ai").warning("llm.probe", engine=engine.alias, model_id=engine.model,
                                 base_url=engine.base_url, error="groq 503 from qwen")
        state = "down" if engine.alias == "primary" else "ok"
        return {"state": state, "latency_ms": 5}

    monkeypatch.setattr(probe, "_probe_engine", fake_probe)
    monkeypatch.setattr(routes_health, "get_settings", lambda: live)
    probe.ai_probe.reset()
    try:
        res = client.get("/api/health")
    finally:
        probe.ai_probe.reset()
    body = res.json()
    assert body["ai"]["status"] == "backup"
    assert body["ai"]["primary"] == "down"
    assert not LEAK.search(res.text)


def test_log_view_is_redacted_and_alias_only(client: TestClient, operator_headers):  # type: ignore[no-untyped-def]
    get_logger("ai").info(
        "llm.response",
        engine="backup",
        model_id="gemini-x",
        provider="google",
        note="fell back from groq",
        password="hunter2",
        dsn="postgresql://user:hunter2@db.example/neondb",
        tokens_in=12,
    )
    res = client.get("/api/ops/logs", params={"event": "llm.response"}, headers=operator_headers)
    assert res.status_code == 200
    items = res.json()["items"]
    assert items, "the event should be in the ring buffer"
    assert not LEAK.search(res.text)
    assert "hunter2" not in res.text
    assert items[0]["tokens_in"] == 12 and items[0]["engine"] == "backup"


def test_agent_run_and_trace_are_alias_only(client: TestClient, operator_headers):  # type: ignore[no-untyped-def]
    from app.agent.gateway import breaker
    from app.agent.mock_llm import mock_client

    mock_client.reset()
    breaker.reset()
    # The primary fails with a vendor-naming error and the model's text names a vendor.
    mock_client.queue("primary", {"content": "As a Qwen model on Groq, I will start."},
                      {"error": "server_error"}, {"error": "server_error"})
    try:
        project = client.post("/api/projects", json={"name": "leak", "dataset_key": "clean_25"},
                              headers=operator_headers).json()
        res = client.post(f"/api/projects/{project['id']}/agent-runs", headers=operator_headers)
        assert res.status_code == 202 and not LEAK.search(res.text)
        run = client.get(f"/api/agent-runs/{res.json()['id']}", headers=operator_headers)
        history = client.get(f"/api/projects/{project['id']}/history", headers=operator_headers)
        logs = client.get("/api/ops/logs", params={"limit": 1000}, headers=operator_headers)
    finally:
        mock_client.reset()
        breaker.reset()
    body = run.json()
    assert body["status"] == "SUCCEEDED" and body["fell_back"] is True
    assert "model_id" not in body
    for response in (run, history, logs):
        assert not LEAK.search(response.text)


def test_logs_filter_by_request_id(client: TestClient, operator_headers):  # type: ignore[no-untyped-def]
    client.get("/api/inputs/datasets", headers={**operator_headers, "X-Request-ID": "trace-me-1"})
    res = client.get("/api/ops/logs", params={"request_id": "trace-me-1"}, headers=operator_headers)
    items = res.json()["items"]
    assert items and all(i["request_id"] == "trace-me-1" for i in items)
    assert any(i["event"] == "http.request" and i["user"] == "operator" for i in items)
