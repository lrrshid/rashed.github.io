"""Business rules stored in APP_SETTING (one JSON value per key). Defaults live in seed/reference_data.SETTINGS;
a key missing from the table answers its default, so a new rule works before anyone saves it."""
from __future__ import annotations

import json
import re

from flask import g, has_request_context
from sqlalchemy import select

from ..exceptions import NotFound, StaleVersion, ValidationFailed
from ..models import AppSetting
from ..security.auth import require_admin
from ..seed.reference_data import SETTINGS as DEFAULTS
from . import audit_service, context


def _cache() -> dict:
    if not has_request_context():
        return {}
    if not hasattr(g, "_settings_cache"):
        g._settings_cache = {}
    return g._settings_cache


def get(key: str):
    cache = _cache()
    if key in cache:
        return cache[key]
    if key not in DEFAULTS:
        raise KeyError(key)
    row = context.session().scalar(select(AppSetting).where(AppSetting.setting_key == key))
    value = json.loads(row.value_json) if row is not None else DEFAULTS[key]
    cache[key] = value
    return value


def all_settings() -> list[dict]:
    rows = {r.setting_key: r for r in context.session().scalars(select(AppSetting))}
    out = []
    for key, default in DEFAULTS.items():
        row = rows.get(key)
        out.append({"key": key, "value": json.loads(row.value_json) if row else default, "default": default,
                    "version": row.version if row else 0})
    return out


def _check_shape(key: str, value) -> None:
    default = DEFAULTS[key]
    if isinstance(default, list):
        if not (isinstance(value, list) and all(isinstance(v, str) and v for v in value)):
            raise ValidationFailed.field("value", "Must be a list of codes.")
    elif isinstance(default, dict):
        if not isinstance(value, dict) or set(value) != set(default):
            raise ValidationFailed.field("value", f"Must have exactly these keys: {', '.join(default)}.")
        for k, v in value.items():
            if isinstance(default[k], (int, float)) and (not isinstance(v, (int, float)) or isinstance(v, bool) or v < 0):
                raise ValidationFailed.field("value", f"{k} must be a number of 0 or more.")
            if isinstance(default[k], str) and not (isinstance(v, str) and 1 <= len(v) <= 200):
                raise ValidationFailed.field("value", f"{k} must be a text of 1 to 200 characters.")
        if key == "ui.theme" and not all(re.fullmatch(r"#[0-9a-fA-F]{6}", v) for v in value.values()):
            raise ValidationFailed.field("value", "Colours must be written as #rrggbb.")
        if key == "readiness.weights" and round(sum(value.values())) != 100:
            raise ValidationFailed.field("value", "The weights must add up to 100.")
    elif isinstance(default, (int, float)):
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
            raise ValidationFailed.field("value", "Must be a number of 0 or more.")


def update(actor, key: str, value, version: int | None, reason: str | None = None) -> dict:
    require_admin(actor)
    if key not in DEFAULTS:
        raise NotFound(f"Setting {key} was not found.")
    _check_shape(key, value)
    session = context.session()
    row = session.scalar(select(AppSetting).where(AppSetting.setting_key == key).with_for_update(of=AppSetting.id))
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True)
    if len(encoded) > 4000:
        raise ValidationFailed.field("value", "The value is too long.")
    now = context.now()
    if row is None:
        if version not in (None, 0):
            raise StaleVersion()
        row = AppSetting(setting_key=key, value_json=encoded)
        context.stamp_create(row, actor, now)
        session.add(row)
        session.flush()
        audit_service.record(actor, "CREATE", row, None, audit_service.snapshot(row), reason)
    else:
        if version is not None:
            context.check_version(row, version)
        if row.value_json != encoded:
            before = audit_service.snapshot(row)
            row.value_json = encoded
            context.stamp_update(row, actor, now)
            session.flush()
            audit_service.record(actor, "UPDATE", row, before, audit_service.snapshot(row), reason)
    session.commit()
    _cache().pop(key, None)
    return next(s for s in all_settings() if s["key"] == key)
