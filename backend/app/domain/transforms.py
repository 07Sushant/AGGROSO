"""Whitelisted pure transforms with typed params (spec §5.2).

No I/O and no ``eval``. Each transform returns a value or raises ``TransformError`` carrying a
typed error code. Each entry declares a Pydantic params model and ``input_type -> output_type`` so
the plan validator can type-check a chain against the target column.

Type vocabulary: ``string``, ``integer``, ``boolean``, ``date``, ``string[]`` (several source
fields), ``none`` (no source field), ``any`` (unknown / mixed: always a type mismatch).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

Scalar = bool | int | str

PHONE_CALLING_CODES: dict[str, str] = {
    "US": "1",
    "CA": "1",
    "IN": "91",
    "GB": "44",
    "DE": "49",
    "FR": "33",
    "AU": "61",
    "SG": "65",
}
# Expected national-number lengths when a number has no "+" prefix.
_NATIONAL_LENGTHS: dict[str, tuple[int, ...]] = {
    "US": (10,),
    "CA": (10,),
    "IN": (10,),
    "GB": (10,),
    "DE": (10, 11),
    "FR": (9,),
    "AU": (9,),
    "SG": (8,),
}


class TransformError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class TransformTypeError(Exception):
    """A chain does not type-check (raised by ``resolve_output_type``)."""


class _Params(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NoParams(_Params):
    pass


class SplitNameParams(_Params):
    part: Literal["first", "last"]


class ParseDateParams(_Params):
    formats: list[str] = Field(min_length=1, max_length=10)

    @field_validator("formats")
    @classmethod
    def _check_formats(cls, formats: list[str]) -> list[str]:
        for fmt in formats:
            if not (2 <= len(fmt) <= 32) or "%" not in fmt:
                raise ValueError(f"'{fmt}' is not a strptime format such as '%Y-%m-%d'")
        return formats


class NormalizePhoneParams(_Params):
    default_country: Literal["US", "CA", "IN", "GB", "DE", "FR", "AU", "SG"]


class MapValuesParams(_Params):
    mapping: dict[str, Scalar] = Field(min_length=1, max_length=200)
    strict: bool = True
    case_insensitive: bool = False

    @model_validator(mode="after")
    def _check_keys(self) -> MapValuesParams:
        if self.case_insensitive:
            lowered = [k.casefold() for k in self.mapping]
            if len(set(lowered)) != len(lowered):
                raise ValueError("mapping keys collide when compared case-insensitively")
        return self


class ParseCurrencyParams(_Params):
    null_values: list[str] = Field(default_factory=list, max_length=20)


class ToBooleanParams(_Params):
    true_values: list[str] = Field(min_length=1, max_length=20)
    false_values: list[str] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def _disjoint(self) -> ToBooleanParams:
        overlap = {v.casefold() for v in self.true_values} & {
            v.casefold() for v in self.false_values
        }
        if overlap:
            raise ValueError(f"values listed as both true and false: {sorted(overlap)}")
        return self


class ConstantParams(_Params):
    value: Scalar


class DefaultIfEmptyParams(_Params):
    value: Scalar


class ConcatParams(_Params):
    separator: str = Field(default=" ", max_length=10)


def scalar_type(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, str):
        return "string"
    if isinstance(value, date):
        return "date"
    return "any"


# --------------------------------------------------------------------------- implementations
def _require_str(value: Any, name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TransformError("TYPE_ERROR", f"{name} expects text, got {scalar_type(value)}")
    return value


def _trim(value: Any, _p: NoParams) -> Any:
    s = _require_str(value, "trim")
    return None if s is None else s.strip()


def _lowercase(value: Any, _p: NoParams) -> Any:
    s = _require_str(value, "lowercase")
    return None if s is None else s.lower()


def _uppercase(value: Any, _p: NoParams) -> Any:
    s = _require_str(value, "uppercase")
    return None if s is None else s.upper()


def _split_name(value: Any, p: SplitNameParams) -> Any:
    s = _require_str(value, "split_name")
    if s is None:
        return None
    s = " ".join(s.split())
    if not s:
        return None
    if "," in s:  # "LAST, First"
        last, _, first = s.partition(",")
        first, last = first.strip(), last.strip()
    else:  # "First Last" (the last token is the last name)
        tokens = s.split(" ")
        if len(tokens) == 1:
            first, last = tokens[0], ""
        else:
            first, last = " ".join(tokens[:-1]), tokens[-1]
    result = first if p.part == "first" else last
    return result or None


def _parse_date(value: Any, p: ParseDateParams) -> Any:
    s = _require_str(value, "parse_date")
    if s is None or not s.strip():
        return None
    s = s.strip()
    for fmt in p.formats:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise TransformError("PARSE_DATE_FAILED", f"'{s}' does not match any of {p.formats}")


def _normalize_phone(value: Any, p: NormalizePhoneParams) -> Any:
    s = _require_str(value, "normalize_phone_e164")
    if s is None or not s.strip():
        return None
    s = s.strip()
    if re.search(r"[A-Za-z]", s):
        raise TransformError("PHONE_INVALID", f"'{s}' contains letters")
    if s.startswith("00"):
        s = "+" + s[2:]
    digits = re.sub(r"\D", "", s)
    if s.startswith("+"):
        e164_digits = digits
    else:
        code = PHONE_CALLING_CODES[p.default_country]
        national = digits
        if code == "1" and len(national) == 11 and national.startswith("1"):
            national = national[1:]
        elif code != "1" and national.startswith("0"):
            national = national[1:]  # drop the trunk prefix
        if len(national) not in _NATIONAL_LENGTHS[p.default_country]:
            raise TransformError(
                "PHONE_INVALID",
                f"'{s}' has {len(national)} digits; expected a {p.default_country} number",
            )
        e164_digits = code + national
    if not (8 <= len(e164_digits) <= 15):
        raise TransformError("PHONE_INVALID", f"'{s}' is not a valid international number")
    return "+" + e164_digits


def _map_values(value: Any, p: MapValuesParams) -> Any:
    s = _require_str(value, "map_values")
    if s is None:
        return None
    if s in p.mapping:
        return p.mapping[s]
    if p.case_insensitive:
        folded = {k.casefold(): v for k, v in p.mapping.items()}
        if s.casefold() in folded:
            return folded[s.casefold()]
    if p.strict:
        raise TransformError("UNMAPPED_VALUE", f"'{s}' has no entry in the value mapping")
    return s


_CURRENCY_RE = re.compile(r"^\d+(\.\d{1,2})?$")


def _parse_currency(value: Any, p: ParseCurrencyParams) -> Any:
    s = _require_str(value, "parse_currency_to_cents")
    if s is None:
        return None
    raw = s.strip()
    if raw == "" or raw.casefold() in {v.strip().casefold() for v in p.null_values}:
        return None
    t = raw.replace(",", "").replace(" ", "")
    t = re.sub(r"(?i)^usd|usd$", "", t)
    negative = False
    if t.startswith("(") and t.endswith(")"):
        negative, t = True, t[1:-1]
    if t.startswith("-"):
        negative, t = True, t[1:]
    t = t.replace("$", "")
    if t.startswith("-"):
        negative, t = True, t[1:]
    if not _CURRENCY_RE.match(t):
        raise TransformError("PARSE_CURRENCY_FAILED", f"'{raw}' is not a currency amount")
    try:
        cents = int(Decimal(t) * 100)
    except InvalidOperation as exc:  # pragma: no cover - guarded by the regex
        raise TransformError("PARSE_CURRENCY_FAILED", f"'{raw}' is not a currency amount") from exc
    return -cents if negative else cents


def _to_boolean(value: Any, p: ToBooleanParams) -> Any:
    s = _require_str(value, "to_boolean")
    if s is None or not s.strip():
        return None
    key = s.strip().casefold()
    if key in {v.casefold() for v in p.true_values}:
        return True
    if key in {v.casefold() for v in p.false_values}:
        return False
    raise TransformError("BOOLEAN_INVALID", f"'{s.strip()}' is not a recognised yes/no value")


def _constant(_value: Any, p: ConstantParams) -> Any:
    return p.value


def _default_if_empty(value: Any, p: DefaultIfEmptyParams) -> Any:
    if value is None or (isinstance(value, str) and not value.strip()):
        return p.value
    return value


def _concat(value: Any, p: ConcatParams) -> Any:
    if value is None:
        return None
    if not isinstance(value, (list, tuple)):
        raise TransformError("TYPE_ERROR", "concat expects several source fields")
    parts = [str(v).strip() for v in value if v is not None and str(v).strip()]
    return p.separator.join(parts) if parts else None


# --------------------------------------------------------------------------- type resolution
def _fixed(output: str) -> Callable[[Any, str], str]:
    def resolve(_params: Any, _input_type: str) -> str:
        return output

    return resolve


def _map_values_type(p: MapValuesParams, _input_type: str) -> str:
    types = {scalar_type(v) for v in p.mapping.values()}
    if not p.strict:
        types.add("string")  # unmapped values pass through unchanged
    if len(types) != 1:
        raise TransformTypeError(
            f"map_values produces mixed types {sorted(types)}; use one value type"
        )
    return types.pop()


def _constant_type(p: ConstantParams, _input_type: str) -> str:
    return scalar_type(p.value)


def _default_type(p: DefaultIfEmptyParams, input_type: str) -> str:
    value_type = scalar_type(p.value)
    if value_type != input_type:
        raise TransformTypeError(
            f"default_if_empty value is {value_type} but the chain produces {input_type}"
        )
    return input_type


@dataclass(frozen=True)
class TransformSpec:
    name: str
    description: str
    params_model: type[_Params]
    input_type: str  # "T" means: any type, passed through
    output_type: str
    fn: Callable[[Any, Any], Any]
    resolve: Callable[[Any, str], str]


_SPECS = [
    TransformSpec("trim", "Remove leading and trailing whitespace.", NoParams,
                  "string", "string", _trim, _fixed("string")),
    TransformSpec("lowercase", "Convert text to lower case.", NoParams,
                  "string", "string", _lowercase, _fixed("string")),
    TransformSpec("uppercase", "Convert text to upper case.", NoParams,
                  "string", "string", _uppercase, _fixed("string")),
    TransformSpec("split_name",
                  "Take the first or last name from 'First Last' or 'LAST, First'. "
                  "A single word yields only a first name.",
                  SplitNameParams, "string", "string", _split_name, _fixed("string")),
    TransformSpec("parse_date", "Parse text into a date, trying each strptime format in order.",
                  ParseDateParams, "string", "date", _parse_date, _fixed("date")),
    TransformSpec("normalize_phone_e164",
                  "Normalise a phone number to E.164. Numbers without '+' use the default "
                  "country's calling code. Empty input gives null.",
                  NormalizePhoneParams, "string", "string", _normalize_phone, _fixed("string")),
    TransformSpec("map_values",
                  "Replace a value using an explicit lookup table. With strict=true an "
                  "unknown value is an error; otherwise it passes through.",
                  MapValuesParams, "string", "value", _map_values, _map_values_type),
    TransformSpec("parse_currency_to_cents",
                  "Parse a currency string such as '$1,200.50' into integer cents. Values in "
                  "null_values (and empty text) give null.",
                  ParseCurrencyParams, "string", "integer", _parse_currency, _fixed("integer")),
    TransformSpec("to_boolean",
                  "Map yes/no text to a boolean (case-insensitive). Empty input gives null.",
                  ToBooleanParams, "string", "boolean", _to_boolean, _fixed("boolean")),
    TransformSpec("constant", "Ignore the source and produce a fixed value.", ConstantParams,
                  "none", "value", _constant, _constant_type),
    TransformSpec("default_if_empty", "Replace null or empty text with a fixed value.",
                  DefaultIfEmptyParams, "T", "T", _default_if_empty, _default_type),
    TransformSpec("concat", "Join several source fields with a separator, skipping empties.",
                  ConcatParams, "string[]", "string", _concat, _fixed("string")),
]

REGISTRY: dict[str, TransformSpec] = {spec.name: spec for spec in _SPECS}


def parse_params(name: str, params: dict[str, Any] | None) -> _Params:
    """Validate params for a transform. Raises KeyError (unknown) or ValidationError."""
    spec = REGISTRY[name]
    return spec.params_model.model_validate(params or {})


def apply_transform(name: str, value: Any, params: dict[str, Any] | _Params | None = None) -> Any:
    spec = REGISTRY[name]
    parsed = params if isinstance(params, _Params) else parse_params(name, params)
    return spec.fn(value, parsed)


def resolve_output_type(name: str, params: _Params, input_type: str) -> str:
    """Type of the transform's output given its input type; raises TransformTypeError."""
    spec = REGISTRY[name]
    if spec.input_type not in ("T", input_type):
        raise TransformTypeError(f"{name} expects {spec.input_type} input but got {input_type}")
    return spec.resolve(params, input_type)


def registry_listing() -> list[dict[str, Any]]:
    return [
        {
            "name": spec.name,
            "description": spec.description,
            "input_type": spec.input_type,
            "output_type": spec.output_type,
            "params_schema": spec.params_model.model_json_schema(),
        }
        for spec in _SPECS
    ]


__all__ = [
    "REGISTRY",
    "TransformError",
    "TransformTypeError",
    "ValidationError",
    "apply_transform",
    "parse_params",
    "registry_listing",
    "resolve_output_type",
]
