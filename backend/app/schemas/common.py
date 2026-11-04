"""Shared request types and query-string parsing.

Normalisation rules (brief section 5/6): trim every string; uppercase codes; blank optional
strings become null (as Oracle would store them); blank required values are rejected.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Annotated, Any, ClassVar

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, model_validator
from pydantic.alias_generators import to_camel

from ..exceptions import ValidationFailed

CODE_RE = re.compile(r"^[A-Z0-9-]+$")
DATE_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 25


def _trim(value: Any) -> Any:
    return value.strip() if isinstance(value, str) else value


def _blank_to_none(value: Any) -> Any:
    value = _trim(value)
    return None if value == "" else value


def _upper(value: Any) -> Any:
    value = _trim(value)
    return value.upper() if isinstance(value, str) else value


def text_length(value: str) -> int:
    """Length in UTF-16 code units: an emoji or other character outside the Basic Multilingual Plane counts as 2.
    That is how Oracle's LENGTH() measures a CLOB (stored as UTF-16, used by the CHECK limits on notes and
    reasons) and how the browser's maxlength counts, so text the form allows is never rejected by the database."""
    return len(value.encode("utf-16-le")) // 2


def required_text(min_len: int, max_len: int):
    def check(value: str) -> str:
        if value == "":
            raise ValueError("This field is required.")
        if len(value) < min_len:
            raise ValueError(f"Must be at least {min_len} characters.")
        if text_length(value) > max_len:
            raise ValueError(f"Must be at most {max_len} characters.")
        return value

    return Annotated[str, BeforeValidator(_trim), AfterValidator(check)]


def optional_text(max_len: int):
    def check(value: str | None) -> str | None:
        if value is not None and text_length(value) > max_len:
            raise ValueError(f"Must be at most {max_len} characters.")
        return value

    return Annotated[str | None, BeforeValidator(_blank_to_none), AfterValidator(check)]


def code_text(min_len: int, max_len: int):
    def check(value: str) -> str:
        if value == "":
            raise ValueError("This field is required.")
        if not (min_len <= len(value) <= max_len):
            raise ValueError(f"Must be {min_len} to {max_len} characters.")
        if not CODE_RE.match(value):
            raise ValueError("Use only letters, digits and hyphens.")
        return value

    return Annotated[str, BeforeValidator(_upper), AfterValidator(check)]


def parse_id(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError("Must be an id.")
    if isinstance(value, int):
        number = value
    elif isinstance(value, str) and re.fullmatch(r"[0-9]{1,19}", value.strip()):  # not isdigit(): '²' or '٣'
        number = int(value.strip())
    else:
        raise ValueError("Must be an id.")
    if number < 1 or number > 9_223_372_036_854_775_807:
        raise ValueError("Must be an id.")
    return number


Id = Annotated[int, BeforeValidator(parse_id)]


def _parse_date(value: Any) -> Any:
    value = _blank_to_none(value)
    if value is None or isinstance(value, date):
        return value
    if not isinstance(value, str) or not DATE_RE.match(value):
        raise ValueError("Use the date format YYYY-MM-DD.")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("Not a valid calendar date.") from exc


DateOnly = Annotated[date | None, BeforeValidator(_parse_date)]


def _version(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError("Version is required.")
    try:
        number = int(value)
    except ValueError as exc:
        raise ValueError("Version must be a number.") from exc
    if number < 1:
        raise ValueError("Version must be a positive number.")
    return number


Version = Annotated[int, BeforeValidator(_version)]


def _number(low: float, high: float, whole: bool):
    def check(value: Any) -> Any:
        if value is None or value == "":
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("Must be a number.")
        if whole and not float(value).is_integer():
            raise ValueError("Must be a whole number.")
        if not (low <= value <= high):
            raise ValueError(f"Must be between {low:g} and {high:g}.")
        return int(value) if whole else float(value)
    return check


Percent = Annotated[int | None, BeforeValidator(_number(0, 100, True))]
Quantity = Annotated[int, BeforeValidator(_number(0, 100000, True))]
Count = Annotated[int | None, BeforeValidator(_number(0, 10_000_000, True))]
Amount = Annotated[float | None, BeforeValidator(_number(0, 99_999_999_999_999, False))]
Reason = optional_text(2000)


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid", alias_generator=to_camel, populate_by_name=False)


class PatchModel(ApiModel):
    """Partial update: only fields present in the body change. Required fields may not be sent as null."""

    REQUIRED_ON_PATCH: ClassVar[tuple[str, ...]] = ()

    @model_validator(mode="after")
    def _no_null_required(self):
        for name in self.REQUIRED_ON_PATCH:
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{to_camel(name)} cannot be empty.")
        return self

    def changes(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in self.model_fields_set if k not in ("version", "reason")}


def parse_body(model: type[BaseModel], payload: Any) -> BaseModel:
    if not isinstance(payload, dict):
        raise ValidationFailed("Request body must be a JSON object.")
    return model.model_validate(payload)


class Query:
    """Strict query-string reader: unknown parameters are rejected rather than silently ignored."""

    def __init__(self, args, allowed: set[str]):
        unknown = sorted(set(args.keys()) - allowed - {"page", "size", "_"})
        if unknown:
            raise ValidationFailed(
                "Unsupported query parameter.", [{"field": name, "message": "Unsupported parameter."} for name in unknown]
            )
        self.args = args

    def page(self) -> tuple[int, int]:
        page = self._int("page", 0)
        size = self._int("size", DEFAULT_PAGE_SIZE)
        if page < 0:
            raise ValidationFailed.field("page", "Must be 0 or greater.")
        if size < 1 or size > MAX_PAGE_SIZE:
            raise ValidationFailed.field("size", f"Must be between 1 and {MAX_PAGE_SIZE}.")
        return page, size

    def _int(self, name: str, default: int) -> int:
        raw = self.args.get(name)
        if raw is None or raw == "":
            return default
        if not re.fullmatch(r"[0-9]{1,9}", raw):
            raise ValidationFailed.field(name, "Must be a whole number.")
        return int(raw)

    def text(self, name: str, max_len: int = 200) -> str | None:
        raw = (self.args.get(name) or "").strip()
        if not raw:
            return None
        if len(raw) > max_len:
            raise ValidationFailed.field(name, f"Must be at most {max_len} characters.")
        return raw

    def choice(self, name: str, allowed: tuple[str, ...] | set[str]) -> str | None:
        raw = (self.args.get(name) or "").strip().upper()
        if not raw:
            return None
        if raw not in allowed:
            raise ValidationFailed.field(name, f"Must be one of: {', '.join(sorted(allowed))}.")
        return raw

    def choices(self, name: str, allowed: tuple[str, ...]) -> list[str]:
        raw = (self.args.get(name) or "").strip().upper()
        if not raw:
            return []
        values = [v.strip() for v in raw.split(",") if v.strip()]
        bad = [v for v in values if v not in allowed]
        if bad:
            raise ValidationFailed.field(name, f"Must be one of: {', '.join(allowed)}.")
        return values

    def id(self, name: str) -> int | None:
        raw = (self.args.get(name) or "").strip()
        if not raw:
            return None
        try:
            return parse_id(raw)
        except ValueError:
            raise ValidationFailed.field(name, "Must be an id.") from None

    def date(self, name: str) -> date | None:
        """A calendar date (YYYY-MM-DD), or None when the parameter is absent or blank."""
        raw = (self.args.get(name) or "").strip()
        if not raw:
            return None
        try:
            return _parse_date(raw)
        except ValueError as exc:
            raise ValidationFailed.field(name, str(exc)) from None

    def boolean(self, name: str) -> bool | None:
        raw = (self.args.get(name) or "").strip().lower()
        if not raw:
            return None
        if raw not in ("true", "false"):
            raise ValidationFailed.field(name, "Must be true or false.")
        return raw == "true"


def page_envelope(items: list, page: int, size: int, total: int) -> dict:
    return {
        "items": items,
        "page": page,
        "size": size,
        "totalItems": total,
        "totalPages": (total + size - 1) // size if total else 0,
    }
