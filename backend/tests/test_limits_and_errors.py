from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.errors import AppError
from app.security import decode_access_token


def _assert_envelope(res, code: str) -> dict:  # type: ignore[no-untyped-def]
    body = res.json()
    assert set(body) == {"error"}
    err = body["error"]
    assert set(err) == {"code", "message", "details", "request_id"}
    assert err["code"] == code
    assert err["request_id"] == res.headers["x-request-id"]
    return err


def test_request_id_is_echoed_or_generated(client: TestClient):
    res = client.get("/api/health/live", headers={"X-Request-ID": "abc-123"})
    assert res.status_code == 200 and res.headers["x-request-id"] == "abc-123"
    generated = client.get("/api/health/live", headers={"X-Request-ID": "bad id with spaces"})
    assert generated.headers["x-request-id"] != "bad id with spaces"
    assert len(generated.headers["x-request-id"]) == 32


def test_unauthenticated_and_not_found_envelopes(client: TestClient):
    _assert_envelope(client.get("/api/inputs/source-schema"), "UNAUTHENTICATED")
    res = client.get("/api/inputs/source-schema", headers={"Authorization": "Bearer nope"})
    assert res.status_code == 401
    _assert_envelope(res, "UNAUTHENTICATED")
    res = client.get("/api/does-not-exist")
    assert res.status_code == 404
    _assert_envelope(res, "NOT_FOUND")


def test_validation_error_envelope_lists_fields(client: TestClient):
    res = client.post("/api/auth/login", json={"username": ""})
    assert res.status_code == 422
    err = _assert_envelope(res, "VALIDATION_ERROR")
    paths = {e["path"] for e in err["details"]["errors"]}
    assert {"body.username", "body.password"} <= paths


def test_internal_errors_hide_details(app, client: TestClient):  # type: ignore[no-untyped-def]
    def boom() -> None:
        raise RuntimeError("secret internals: postgresql://user:pw@host/db")

    def forbidden() -> None:
        raise AppError("FORBIDDEN", "Not for you.")

    app.add_api_route("/api/_test/boom", boom)
    app.add_api_route("/api/_test/forbidden", forbidden)
    res = client.get("/api/_test/boom")
    assert res.status_code == 500
    err = _assert_envelope(res, "INTERNAL")
    assert "secret" not in res.text and "postgresql" not in res.text
    assert err["message"] == "An unexpected error occurred."
    res = client.get("/api/_test/forbidden")
    assert res.status_code == 403
    _assert_envelope(res, "FORBIDDEN")


def test_login_roles_and_me(client: TestClient, operator_headers, approver_headers):  # type: ignore[no-untyped-def]
    bad = client.post("/api/auth/login", json={"username": "operator", "password": "wrong"})
    assert bad.status_code == 401
    _assert_envelope(bad, "UNAUTHENTICATED")
    unknown = client.post("/api/auth/login", json={"username": "nobody", "password": "x"})
    assert unknown.status_code == 401

    me = client.get("/api/auth/me", headers=operator_headers).json()
    assert me["username"] == "operator" and me["role"] == "operator"
    token = approver_headers["Authorization"].split(" ", 1)[1]
    assert decode_access_token(token).role == "approver"


@pytest.mark.parametrize(
    "path", ["/api/inputs/source-schema", "/api/inputs/target-schema", "/api/inputs/transforms"]
)
def test_inputs_are_served(client: TestClient, operator_headers, path):  # type: ignore[no-untyped-def]
    res = client.get(path, headers=operator_headers)
    assert res.status_code == 200 and res.json()


def test_overflow_dataset_is_refused_with_limit_exceeded(client: TestClient, operator_headers):  # type: ignore[no-untyped-def]
    res = client.post("/api/projects", json={"name": "too big", "dataset_key": "overflow_501"},
                      headers=operator_headers)
    assert res.status_code == 422
    err = _assert_envelope(res, "LIMIT_EXCEEDED")
    assert err["details"] == {"record_count": 501, "max_source_records": 500}
    ok = client.post("/api/projects", json={"name": "max", "dataset_key": "stress_500"},
                     headers=operator_headers)
    assert ok.status_code == 201 and ok.json()["record_count"] == 500


def test_datasets_flag_the_overflow_limit(client: TestClient, operator_headers):  # type: ignore[no-untyped-def]
    res = client.get("/api/inputs/datasets", headers=operator_headers)
    by_key = {d["key"]: d for d in res.json()}
    assert by_key["baseline_60"]["record_count"] == 60
    assert by_key["stress_500"]["within_limit"] is True
    assert by_key["overflow_501"]["within_limit"] is False
