from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from app.domain.transforms import (
    REGISTRY,
    TransformError,
    TransformTypeError,
    apply_transform,
    parse_params,
    registry_listing,
    resolve_output_type,
)

DATE_FORMATS = {"formats": ["%Y-%m-%d", "%d/%m/%Y", "%b %d, %Y", "%Y%m%d"]}
BOOL_PARAMS = {"true_values": ["Y", "YES"], "false_values": ["N", "NO"]}


@pytest.mark.parametrize(
    ("name", "value", "params", "expected"),
    [
        ("trim", "  a b  ", None, "a b"),
        ("trim", None, None, None),
        ("lowercase", "Alice@Example.COM", None, "alice@example.com"),
        ("uppercase", "u.s.", None, "U.S."),
        ("split_name", "Alice Johnson", {"part": "first"}, "Alice"),
        ("split_name", "Alice Johnson", {"part": "last"}, "Johnson"),
        ("split_name", "Johnson, Alice", {"part": "first"}, "Alice"),
        ("split_name", "Johnson, Alice", {"part": "last"}, "Johnson"),
        ("split_name", "Cher", {"part": "first"}, "Cher"),
        ("split_name", "Cher", {"part": "last"}, None),  # mononym: no last name
        ("parse_date", "2021-03-15", DATE_FORMATS, date(2021, 3, 15)),
        ("parse_date", "15/03/2021", DATE_FORMATS, date(2021, 3, 15)),
        ("parse_date", "Mar 15, 2021", DATE_FORMATS, date(2021, 3, 15)),
        ("parse_date", "20210315", DATE_FORMATS, date(2021, 3, 15)),
        ("parse_date", "", DATE_FORMATS, None),
        ("normalize_phone_e164", "(415) 555-0132", {"default_country": "US"}, "+14155550132"),
        ("normalize_phone_e164", "415.555.0132", {"default_country": "US"}, "+14155550132"),
        ("normalize_phone_e164", "1-415-555-0132", {"default_country": "US"}, "+14155550132"),
        ("normalize_phone_e164", "+91 98765 43210", {"default_country": "US"}, "+919876543210"),
        ("normalize_phone_e164", "", {"default_country": "US"}, None),
        ("map_values", "USA", {"mapping": {"USA": "US"}}, "US"),
        ("map_values", "x", {"mapping": {"a": "b"}, "strict": False}, "x"),
        ("map_values", "usa", {"mapping": {"USA": "US"}, "case_insensitive": True}, "US"),
        ("parse_currency_to_cents", "$1,200.50", {}, 120050),
        ("parse_currency_to_cents", "1500", {}, 150000),
        ("parse_currency_to_cents", "-500", {}, -50000),  # parsed; the range rule rejects it
        ("parse_currency_to_cents", "N/A", {"null_values": ["N/A"]}, None),
        ("parse_currency_to_cents", "", {}, None),
        ("to_boolean", "y", BOOL_PARAMS, True),
        ("to_boolean", "N", BOOL_PARAMS, False),
        ("to_boolean", "", BOOL_PARAMS, None),
        ("constant", None, {"value": "standard"}, "standard"),
        ("default_if_empty", None, {"value": False}, False),
        ("default_if_empty", True, {"value": False}, True),
        ("concat", ["Alice", "", "Johnson"], {"separator": " "}, "Alice Johnson"),
    ],
)
def test_transform_values(name, value, params, expected):  # type: ignore[no-untyped-def]
    assert apply_transform(name, value, params) == expected


@pytest.mark.parametrize(
    ("name", "value", "params", "code"),
    [
        ("parse_date", "31/02/2020", DATE_FORMATS, "PARSE_DATE_FAILED"),
        ("parse_date", "unknown", DATE_FORMATS, "PARSE_DATE_FAILED"),
        ("map_values", "Atlantis", {"mapping": {"USA": "US"}}, "UNMAPPED_VALUE"),
        ("parse_currency_to_cents", "lots", {}, "PARSE_CURRENCY_FAILED"),
        ("parse_currency_to_cents", "1.234", {}, "PARSE_CURRENCY_FAILED"),
        ("normalize_phone_e164", "555-01", {"default_country": "US"}, "PHONE_INVALID"),
        ("normalize_phone_e164", "call me", {"default_country": "US"}, "PHONE_INVALID"),
        ("to_boolean", "maybe", BOOL_PARAMS, "BOOLEAN_INVALID"),
        ("trim", 42, None, "TYPE_ERROR"),
        ("concat", "not-a-list", {}, "TYPE_ERROR"),
    ],
)
def test_transform_errors_are_typed(name, value, params, code):  # type: ignore[no-untyped-def]
    with pytest.raises(TransformError) as exc:
        apply_transform(name, value, params)
    assert exc.value.code == code


@pytest.mark.parametrize(
    ("name", "params"),
    [
        ("split_name", {"part": "middle"}),
        ("trim", {"unexpected": 1}),
        ("parse_date", {"formats": []}),
        ("parse_date", {"formats": ["YYYY-MM-DD"]}),
        ("normalize_phone_e164", {"default_country": "ZZ"}),
        ("to_boolean", {"true_values": ["Y"], "false_values": ["y"]}),
    ],
)
def test_bad_params_are_rejected(name, params):  # type: ignore[no-untyped-def]
    with pytest.raises(ValidationError):
        parse_params(name, params)


def test_type_resolution_along_a_chain():
    p = parse_params("map_values", {"mapping": {"A": "active"}})
    assert resolve_output_type("map_values", p, "string") == "string"
    with pytest.raises(TransformTypeError):
        resolve_output_type("trim", parse_params("trim", None), "date")
    with pytest.raises(TransformTypeError):
        resolve_output_type("default_if_empty", parse_params("default_if_empty", {"value": 1}),
                            "boolean")
    mixed = parse_params("map_values", {"mapping": {"A": "x", "B": True}})
    with pytest.raises(TransformTypeError):
        resolve_output_type("map_values", mixed, "string")


def test_registry_has_twelve_documented_transforms():
    listing = registry_listing()
    assert len(REGISTRY) == 12 == len(listing)
    assert all(item["params_schema"]["type"] == "object" for item in listing)
