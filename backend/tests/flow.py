"""Small API helpers shared by the core tests (each test works in its own project)."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi.testclient import TestClient

from app.db import session_factory


def db_session():  # type: ignore[no-untyped-def]
    return session_factory()()


def create_project(client: TestClient, op: dict, dataset: str = "baseline_60") -> dict:
    res = client.post("/api/projects", json={"name": f"t-{dataset}", "dataset_key": dataset},
                      headers=op)
    assert res.status_code == 201, res.text
    return res.json()


def load_reference(client: TestClient, op: dict, project_id: int) -> dict:
    res = client.post(f"/api/projects/{project_id}/plan-versions/reference", headers=op)
    assert res.status_code == 201, res.text
    return res.json()


def ack_high_risks(client: TestClient, headers: dict, version: dict) -> dict:
    res = client.post(f"/api/plan-versions/{version['id']}/risk-acks",
                      json={"risk_ids": version["unacknowledged_high_risk_ids"]}, headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


def dry_run(client: TestClient, op: dict, version_id: int) -> dict:
    res = client.post(f"/api/plan-versions/{version_id}/dry-runs", headers=op)
    assert res.status_code == 201, res.text
    return res.json()


def approve(client: TestClient, ap: dict, version_id: int) -> dict:
    res = client.post(f"/api/plan-versions/{version_id}/approve", json={"comment": "ok"},
                      headers=ap)
    assert res.status_code == 200, res.text
    return res.json()


def approved_version(client: TestClient, op: dict, ap: dict,
                     dataset: str = "baseline_60") -> tuple[dict, dict]:
    """Project + reference plan, risks acknowledged, dry run, approved. Returns (project, v)."""
    project = create_project(client, op, dataset)
    version = load_reference(client, op, project["id"])
    version = ack_high_risks(client, op, version)
    dry_run(client, op, version["id"])
    approve(client, ap, version["id"])
    return project, version


def new_key() -> str:
    return f"test-{uuid.uuid4().hex}"


def execute(client: TestClient, op: dict, version_id: int, key: str | None = None,
            **body: Any):  # type: ignore[no-untyped-def]
    return client.post(f"/api/plan-versions/{version_id}/runs", json=body or None,
                       headers={**op, "Idempotency-Key": key or new_key()})
