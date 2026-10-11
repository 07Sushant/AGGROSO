from __future__ import annotations

from datetime import date

import pytest

from app.domain.validation import DuplicateTracker, unique_columns, validate_record

VALID = {
    "legacy_id": "C1", "first_name": "Ada", "last_name": "Lovelace",
    "email": "ada@example.com", "phone_e164": "+14155550101",
    "signup_date": date(2020, 1, 2), "country_code": "GB", "status": "active",
    "credit_limit_cents": 1000, "marketing_opt_in": True, "account_tier": "standard",
}
EVIDENCE_KEYS = {"target_field", "source_fields", "source_value", "transform", "rule", "code",
                 "message", "stage"}


def test_valid_record_has_no_errors():
    assert validate_record(dict(VALID), {}) == []


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("email", "", "REQUIRED_FIELD_EMPTY"),
        ("last_name", None, "REQUIRED_FIELD_EMPTY"),
        ("email", "not-an-email", "REGEX_MISMATCH"),
        ("country_code", "ZZ", "ENUM_MISMATCH"),
        ("credit_limit_cents", -50000, "RANGE"),
        ("signup_date", "2020-01-02", "TYPE_MISMATCH"),
        ("marketing_opt_in", "Y", "TYPE_MISMATCH"),
    ],
)
def test_rules_report_field_level_evidence(field, value, code):  # type: ignore[no-untyped-def]
    record = {**VALID, field: value}
    errors = validate_record(record, {field: (["src_col"], "raw")})
    assert [e["code"] for e in errors] == [code]
    err = errors[0]
    assert EVIDENCE_KEYS <= set(err)
    assert err["target_field"] == field and err["stage"] == "validate"
    assert err["source_fields"] == ["src_col"] and err["source_value"] == "raw"


def test_nullable_fields_may_be_empty():
    assert validate_record({**VALID, "phone_e164": None, "credit_limit_cents": None}, {}) == []


def test_duplicates_first_row_wins():
    tracker = DuplicateTracker("legacy_id", unique_columns())
    assert tracker.check(1, VALID, {}) == []
    same_key = tracker.check(2, {**VALID, "email": "other@example.com"}, {})
    assert same_key[0]["code"] == "DUPLICATE_SOURCE_KEY" and same_key[0]["first_row_number"] == 1
    same_email = tracker.check(3, {**VALID, "legacy_id": "C2", "email": " ADA@example.com"}, {})
    assert same_email[0]["code"] == "DUPLICATE_EMAIL" and same_email[0]["first_row_number"] == 1
    assert tracker.check(4, {**VALID, "legacy_id": "C3", "email": "c3@example.com"}, {}) == []
