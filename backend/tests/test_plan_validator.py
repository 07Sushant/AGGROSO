from __future__ import annotations

import copy
from collections.abc import Callable
from typing import Any

import pytest

from app.agent.plan_validator import validate_plan
from app.services import inputs


def _plan() -> dict[str, Any]:
    return copy.deepcopy(inputs.reference_plan()["plan"])


def _mapping(plan: dict[str, Any], target: str) -> dict[str, Any]:
    return next(m for m in plan["mappings"] if m["target_field"] == target)


def test_accepts_the_reference_plan():
    result = validate_plan(_plan())
    assert result.valid, result.errors
    assert result.to_dict()["plan"]["mappings"][0]["on_error"] == "quarantine"


def _invent_source(p):  # type: ignore[no-untyped-def]
    _mapping(p, "email")["source_fields"] = ["email_address"]


def _invent_target(p):  # type: ignore[no-untyped-def]
    p["mappings"].append({**_mapping(p, "email"), "id": "m_x", "target_field": "loyalty_pts"})


def _unknown_transform(p):  # type: ignore[no-untyped-def]
    _mapping(p, "email")["transforms"].append({"name": "eval_python"})


def _bad_params(p):  # type: ignore[no-untyped-def]
    _mapping(p, "first_name")["transforms"][1]["params"] = {"part": "middle"}


def _double_mapped(p):  # type: ignore[no-untyped-def]
    p["mappings"].append({**_mapping(p, "email"), "id": "m_email_2"})


def _uncovered(p):  # type: ignore[no-untyped-def]
    p["mappings"] = [m for m in p["mappings"] if m["target_field"] != "signup_date"]


def _illegal_set_null(p):  # type: ignore[no-untyped-def]
    _mapping(p, "email")["on_error"] = "set_null"


def _type_mismatch(p):  # type: ignore[no-untyped-def]
    _mapping(p, "signup_date")["transforms"] = [{"name": "trim"}]


def _wrong_key(p):  # type: ignore[no-untyped-def]
    p["key"]["target_field"] = "email"


def _duplicate_question(p):  # type: ignore[no-untyped-def]
    p["clarification_questions"].append(dict(p["clarification_questions"][0]))


def _structural(p):  # type: ignore[no-untyped-def]
    p["mappings"][0]["confidence"] = "certain"


@pytest.mark.parametrize(
    ("mutate", "code"),
    [
        (_invent_source, "UNKNOWN_SOURCE_FIELD"),
        (_invent_target, "UNKNOWN_TARGET_FIELD"),
        (_unknown_transform, "UNKNOWN_TRANSFORM"),
        (_bad_params, "INVALID_TRANSFORM_PARAMS"),
        (_double_mapped, "DUPLICATE_TARGET_MAPPING"),
        (_uncovered, "REQUIRED_TARGET_UNMAPPED"),
        (_illegal_set_null, "SET_NULL_NOT_ALLOWED"),
        (_type_mismatch, "TYPE_MISMATCH"),
        (_wrong_key, "INVALID_KEY"),
        (_duplicate_question, "DUPLICATE_ID"),
        (_structural, "SCHEMA_INVALID"),
    ],
)
def test_rejects_invalid_plans(mutate: Callable[[dict], None], code: str):
    plan = _plan()
    mutate(plan)
    result = validate_plan(plan)
    assert not result.valid
    assert code in {e["code"] for e in result.errors}
    assert all(set(e) == {"code", "path", "message"} for e in result.errors)


def test_set_null_is_allowed_on_nullable_targets():
    plan = _plan()
    _mapping(plan, "phone_e164")["on_error"] = "set_null"
    assert validate_plan(plan).valid
