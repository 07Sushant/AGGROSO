"""Screenshot import: the model only proposes; code normalises and a human approves."""
from __future__ import annotations

import json

from app.agent.gateway import LLMResult
from app.services import schema_imports

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64

PROPOSAL = {
    "table_name": "Legacy Customers",
    "fields": [
        {"name": "cust_id", "type": "VARCHAR(20)", "primary_key": True, "confidence": 0.95},
        {"name": "EmailAddr", "type": "varchar", "confidence": 0.9},
        {"name": "signup_dt", "type": "DATE", "confidence": 0.4},
        {"name": "blob", "type": "geometry", "confidence": 0.9},
        {"name": "cust_id", "type": "int"},
    ],
}


class _FakeGateway:
    def chat(self, messages, **_kw):  # type: ignore[no-untyped-def]
        return LLMResult(engine="primary", content=json.dumps(PROPOSAL), tool_calls=[],
                         assistant_message={})


def _upload(client, headers, data=PNG, name="s.png"):  # type: ignore[no-untyped-def]
    return client.post("/api/schema-imports", files={"file": (name, data, "image/png")},
                       headers=headers)


def test_normalises_flags_and_compares(client, operator_headers, monkeypatch):  # type: ignore[no-untyped-def]
    monkeypatch.setattr(schema_imports, "get_gateway", lambda *_a: _FakeGateway())
    res = _upload(client, operator_headers)
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["status"] == "PROPOSED" and body["engine"] == "primary"
    names = [f["name"] for f in body["normalized"]["fields"]]
    assert names == ["cust_id", "email_addr", "signup_dt", "blob"]  # duplicate dropped
    codes = {f["code"] for f in body["findings"]}
    assert {"DUPLICATE_FIELD", "UNKNOWN_TYPE", "LOW_CONFIDENCE", "RENAMED"} <= codes
    cmp = body["comparison"]
    assert {"cust_id", "email_addr", "signup_dt"} <= set(cmp["matched"])
    assert "full_name" in cmp["missing"] and "blob" in cmp["extra"]
    assert {"field": "signup_dt", "expected": "string", "actual": "date"} in cmp["type_mismatch"]
    assert "groq" not in res.text.lower() and "gemini" not in res.text.lower()


def test_rejects_non_image_and_oversized(client, operator_headers):  # type: ignore[no-untyped-def]
    assert _upload(client, operator_headers, b"not an image").status_code == 422
    big = PNG + b"\x00" * (schema_imports.MAX_BYTES + 1)
    assert _upload(client, operator_headers, big).status_code == 422


def test_approval_requires_types_and_approver(client, operator_headers, approver_headers,
                                              monkeypatch):  # type: ignore[no-untyped-def]
    monkeypatch.setattr(schema_imports, "get_gateway", lambda *_a: _FakeGateway())
    imp = _upload(client, operator_headers).json()
    url = f"/api/schema-imports/{imp['id']}/approve"
    assert client.post(url, json={}, headers=operator_headers).status_code == 403
    unknown = client.post(url, json={}, headers=approver_headers)
    assert unknown.status_code == 422 and "blob" in unknown.text
    fields = [{**f, "type": "string" if f["type"] == "unknown" else f["type"]}
              for f in imp["normalized"]["fields"]]
    ok = client.post(url, json={"normalized": {"fields": fields}}, headers=approver_headers)
    assert ok.status_code == 200 and ok.json()["status"] == "APPROVED"
    again = client.post(url, json={"normalized": {"fields": fields}}, headers=approver_headers)
    assert again.status_code == 409
