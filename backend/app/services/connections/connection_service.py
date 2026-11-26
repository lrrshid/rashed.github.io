"""Settings > connections: the company directory and the main database (ported from the Asset Availability project's
Settings tab; system administrators only, owner choice 24 Nov 2026).

The workflow is: edit -> save draft -> test -> apply. A connection has at most one DRAFT revision (edited in place, with
optimistic locking) and at most one ACTIVE one. Applying makes the draft active in one transaction (the old active
revision becomes SUPERSEDED and is kept for rollback), raises the configuration generation so every process picks it
up, and only after:
- every required field and secret is present and valid;
- every required test stage PASSED (or WARNING) for exactly this draft (its fingerprint) within TEST_FRESH_MINUTES; an
  edit makes earlier results stale, so a changed draft must be tested again;
- the password was typed again within the last minutes (auth.require_recent_reauth).
Secrets are never returned: only whether one is saved. Leaving a secret out keeps it, "replace" sets a new one,
"clear" deletes it; a masked placeholder is refused, so it can never overwrite a real secret.
The sign-in method cannot move to the directory without a passed test sign-in by an active administrator (so at least
one administrator can come in) and, outside a local laptop, a ready break-glass account; the connection in use for
sign-in cannot be switched off or deleted. Every change is audited without secret values.
The main database (restart_required) never changes the running app: applying it "stages" the tested revision for a
planned restart (database_provider.py), it has no on/off switch, and it is "in use" when the running connection (.env)
points at the same database.
"""
from __future__ import annotations

import collections
import hashlib
import hmac
import json
import threading
import time
from datetime import timedelta

from flask import current_app
from sqlalchemy import func, select

from ...core import secretbox
from ...core.clock import iso_utc
from ...extensions import db
from ...exceptions import Conflict, NotFound, TooManyAttempts, ValidationFailed
from ...models import (AppRole, AppUser, AuditEvent, ConnectionSetting, EgressRule, ProcessHeartbeat, SettingCert,
                       SettingProfile, SettingRevision, SettingTest)
from ...models.base import Base
from ...models.connections import ACTIVE, DISCARDED, DRAFT, SUPERSEDED
from ...security.auth import BREAK_GLASS_PASSWORD_NOTE, PERM_ADMIN, require_recent_reauth
from .. import audit_service, context
from . import certs, config_service, database_provider, egress, ldap_provider, registry
from .config_service import CONFIG_GENERATION, SIGN_IN_METHOD, SIGN_IN_METHODS

TEST_FRESH_MINUTES = 60          # a passed test older than this must be run again before apply / the method switch
HEALTH_STALE_HOURS = 24          # an older test says nothing about health now ("Stale")
TESTS_PER_MINUTE = 6             # per administrator and connection: tests reach real servers
# SETTING_TEST.code of a passed test sign-in: whether that account could administer the app (the switch needs one).
SIGN_IN_ADMIN, SIGN_IN_NOT_ADMIN = "ADMIN_SIGNED_IN", "NOT_ADMIN"
_PLACEHOLDERS = {"********", "••••••••", "configured", "(set, not shown)"}
_test_lock = threading.Lock()


# ---- small helpers -------------------------------------------------------------------------------------------------

def _keys() -> tuple:
    return current_app.config["SETTINGS"].settings_keys


def _provider(profile: SettingProfile) -> registry.Provider:
    found = registry.get(profile.kind, profile.provider)
    if found is None:
        raise Conflict(f"Settings does not know the provider {profile.provider}.", code="UNKNOWN_PROVIDER")
    return found


def _profile(profile_id: int, for_update: bool = False) -> SettingProfile:
    query = select(SettingProfile).where(SettingProfile.id == profile_id)
    found = context.session().scalar(query.with_for_update() if for_update else query)
    if found is None or found.archived_at is not None:
        raise NotFound(f"Connection {profile_id} was not found.")
    return found


def _revision(revision_id: int | None) -> SettingRevision | None:
    return context.session().get(SettingRevision, revision_id) if revision_id else None


def _draft(profile: SettingProfile) -> SettingRevision | None:
    return context.session().scalar(select(SettingRevision).where(
        SettingRevision.profile_id == profile.id, SettingRevision.state == DRAFT))


def _tokens(revision: SettingRevision | None) -> dict:
    return json.loads(revision.secrets_json) if revision is not None and revision.secrets_json else {}


def _fingerprint(provider: registry.Provider, values: dict, secret_ids: dict, revision_no: int = 0) -> str:
    """Of the exact values and secrets (by their encrypted token, or a keyed digest of an unsaved one) of one revision
    (0: an unsaved candidate): an HMAC under the settings key, so even a fingerprint reveals nothing about a secret.
    The revision number is part of it, so a new draft (a rollback too) needs its own tests."""
    text = json.dumps({"p": provider.id, "s": provider.schema_version, "v": values, "k": secret_ids,
                       "r": revision_no}, sort_keys=True, separators=(",", ":"))
    key = (_keys() or (b"no-key",))[0]
    return hmac.new(key, text.encode("utf-8"), hashlib.sha256).hexdigest()


def _secret_digest(value: str) -> str:
    key = (_keys() or (b"no-key",))[0]
    return "new:" + hmac.new(key, value.encode("utf-8"), hashlib.sha256).hexdigest()


def _audit_setting(actor, name: str, before: str | None, after: str, reason: str | None = None) -> None:
    context.session().add(AuditEvent(actor_id=actor.id, action="UPDATE", entity_type="CONNECTION_SETTING", entity_id=0,
                                     occurred_at=context.now(),
                                     before_json=json.dumps({"name": name, "value": before}, sort_keys=True),
                                     after_json=json.dumps({"name": name, "value": after}, sort_keys=True),
                                     reason=reason))


def _bump_generation(actor) -> None:
    session = context.session()
    row = session.get(ConnectionSetting, CONFIG_GENERATION)
    if row is None:
        session.add(ConnectionSetting(name=CONFIG_GENERATION, value="1", updated_at=context.now(), updated_by=actor.id))
    else:
        row.value = str(int(row.value) + 1)
        row.updated_at, row.updated_by = context.now(), actor.id


def _sign_in_method() -> tuple[str, str, ConnectionSetting | None]:
    """(local | ldap, SETTINGS | ENV, the row when Settings saved one)."""
    row = context.session().get(ConnectionSetting, SIGN_IN_METHOD)
    if row is not None:
        return row.value, "SETTINGS", row
    base = current_app.config["SETTINGS"]
    return ("ldap" if base.auth_mode == "ldap" else "local"), "ENV", None


def _in_use(profile: SettingProfile) -> list[str]:
    """What stops working without this connection."""
    uses = []
    if profile.kind == "DATABASE" and profile.active_revision_id:
        active = _revision(profile.active_revision_id)
        key = database_provider.candidate_key(profile.provider, json.loads(active.fields_json))
        if key and key == database_provider.running_key(current_app.config["SETTINGS"]):
            uses.append("MAIN_DATABASE")
    if profile.kind == "LDAP" and profile.enabled and profile.active_revision_id:
        method, _source, _row = _sign_in_method()
        if method == "ldap":
            uses.append("SIGN_IN")
    return uses


def _rate_limit(actor, profile_id: int) -> None:
    key, now = (actor.id, profile_id), time.monotonic()
    with _test_lock:  # per app (and so per process): tests reach real servers
        times = current_app.extensions.setdefault("connection_test_times",
                                                  collections.defaultdict(collections.deque))[key]
        while times and now - times[0] > 60:
            times.popleft()
        if len(times) >= TESTS_PER_MINUTE:
            raise TooManyAttempts("Too many tests in a minute. Wait a moment and try again.")
        times.append(now)


# ---- reading -------------------------------------------------------------------------------------------------------

def _latest_tests(profile_id: int, fingerprint: str | None) -> list[dict]:
    if not fingerprint:
        return []
    rows = context.session().scalars(select(SettingTest).where(
        SettingTest.profile_id == profile_id, SettingTest.fingerprint == fingerprint)
        .order_by(SettingTest.tested_at.desc(), SettingTest.id.desc()))
    seen, out = set(), []
    for row in rows:
        if row.stage in seen:
            continue
        seen.add(row.stage)
        out.append({"stage": row.stage, "outcome": row.outcome, "code": row.code, "message": row.message,
                    "latencyMs": row.latency_ms, "testedAt": iso_utc(row.tested_at),
                    "testedBy": _user_name(row.tested_by)})
    return out


def _user_name(user_id: int | None) -> str | None:
    if user_id is None:
        return None
    user = context.session().get(AppUser, user_id)
    return user.display_name if user else None


def _health(provider: registry.Provider, tests: list[dict]) -> str:
    """UNTESTED, HEALTHY, DEGRADED, FAILED or STALE, from the latest result of each stage for one fingerprint."""
    if not tests:
        return "UNTESTED"
    by_stage = {t["stage"]: t for t in tests}
    newest = max(t["testedAt"] for t in tests)
    if newest < iso_utc(context.now() - timedelta(hours=HEALTH_STALE_HOURS)):
        return "STALE"
    outcomes = [by_stage[s]["outcome"] for s in provider.required_stages if s in by_stage]
    if "FAILED" in outcomes:
        return "FAILED"
    if len(outcomes) < len(provider.required_stages):
        return "UNTESTED"
    return "DEGRADED" if "WARNING" in outcomes else "HEALTHY"


def _ready(provider: registry.Provider, revision: SettingRevision, tests: list[dict]) -> list[str]:
    """Why this draft cannot be applied yet (empty: it can)."""
    reasons = []
    if provider.status != registry.SUPPORTED:
        return ["FUTURE"]
    values = json.loads(revision.fields_json)
    _out, problems = registry.validate(provider, values, complete=True)
    if problems:
        reasons.append("INVALID")
    tokens = _tokens(revision)
    if any(s not in tokens for s in provider.required_secrets):
        reasons.append("SECRET_MISSING")
    fresh = iso_utc(context.now() - timedelta(minutes=TEST_FRESH_MINUTES))
    by_stage = {t["stage"]: t for t in tests}
    for stage in provider.required_stages:
        test = by_stage.get(stage)
        if test is None or test["outcome"] not in ("PASSED", "WARNING") or test["testedAt"] < fresh:
            reasons.append("NOT_TESTED")
            break
    return reasons


def _revision_dto(provider: registry.Provider, revision: SettingRevision | None, profile_id: int) -> dict | None:
    if revision is None:
        return None
    values = json.loads(revision.fields_json)
    tokens = _tokens(revision)
    _out, problems = registry.validate(provider, values, complete=True)
    tests = _latest_tests(profile_id, revision.fingerprint)
    tests.sort(key=lambda t: provider.stages.index(t["stage"]) if t["stage"] in provider.stages else len(provider.stages))
    return {
        "id": str(revision.id), "revisionNo": revision.revision_no, "state": revision.state,
        "version": revision.version, "fields": values,
        # Never the value: whether one is saved, and when the key that saved it is still configured.
        "secrets": {name: {"configured": name in tokens,
                           "keyKnown": name not in tokens or secretbox.token_key_id(tokens[name]) in
                           {secretbox.key_id(k) for k in _keys()}}
                    for name in provider.secrets},
        "problems": problems, "note": revision.note, "fingerprint": revision.fingerprint[:12],
        "updatedAt": iso_utc(revision.updated_at), "updatedBy": _user_name(revision.updated_by),
        "tests": tests, "health": _health(provider, tests),
    }


def profile_dto(profile: SettingProfile, detail: bool = False) -> dict:
    provider = registry.get(profile.kind, profile.provider)
    active = _revision(profile.active_revision_id)
    draft = _draft(profile)
    active_dto = _revision_dto(provider, active, profile.id) if provider else None
    draft_health = (_health(provider, _latest_tests(profile.id, draft.fingerprint))
                    if provider is not None and draft is not None else None)
    in_use = _in_use(profile)
    if active is None:
        state = "DRAFT" if draft is not None else "NOT_CONFIGURED"
    elif provider is not None and provider.restart_required:
        state = "IN_USE" if "MAIN_DATABASE" in in_use else "STAGED"  # waiting for the planned restart
    else:
        state = "ACTIVE" if profile.enabled else "DISABLED"
    out = {
        "id": str(profile.id), "kind": profile.kind, "provider": profile.provider, "name": profile.name,
        "description": profile.description, "purpose": profile.purpose, "enabled": bool(profile.enabled),
        "version": profile.version, "state": state,
        # The active revision's health; before the first apply, the draft's latest tests.
        "health": active_dto["health"] if active_dto else (draft_health or "NOT_CONFIGURED"),
        "restartRequired": bool(provider and provider.restart_required),
        "activeRevisionNo": active.revision_no if active else None,
        "activeSince": iso_utc(active.updated_at) if active else None,
        "activeBy": _user_name(active.updated_by) if active else None,
        "pendingDraft": draft is not None, "inUse": in_use,
        "updatedAt": iso_utc(profile.updated_at), "updatedBy": _user_name(profile.updated_by),
    }
    if detail and provider is not None:
        draft_dto = _revision_dto(provider, draft, profile.id)
        if draft_dto is not None:
            draft_dto["blockers"] = _ready(provider, draft, draft_dto["tests"])
        if provider.kind == "DATABASE" and active is not None:
            values = json.loads(active.fields_json)
            out["cutover"] = {"envLines": database_provider.env_lines(provider.id, values),
                              "expectedVersion": database_provider.expected_version(
                                  "sqlite" if provider.id == "sqlite" else "oracle"),
                              "setupCommand": database_provider.SETUP_COMMAND}
        out.update(active=active_dto, draft=draft_dto, schema=provider.describe(),
                   revisions=[{"id": str(r.id), "revisionNo": r.revision_no, "state": r.state,
                               "updatedAt": iso_utc(r.updated_at), "updatedBy": _user_name(r.updated_by),
                               "note": r.note}
                              for r in context.session().scalars(select(SettingRevision).where(
                                  SettingRevision.profile_id == profile.id).order_by(SettingRevision.revision_no.desc()))])
    return out


def list_profiles(kind: str | None) -> dict:
    query = select(SettingProfile).where(SettingProfile.archived_at.is_(None))
    if kind:
        query = query.where(SettingProfile.kind == kind)
    return {"items": [profile_dto(p) for p in context.session().scalars(query.order_by(SettingProfile.kind,
                                                                                       SettingProfile.name))]}


def get_profile(profile_id: int) -> dict:
    return profile_dto(_profile(profile_id), detail=True)


def providers() -> dict:
    base = current_app.config["SETTINGS"]
    return {"items": [p.describe() for p in registry.all_providers()
                      if not p.app_profiles or base.profile in p.app_profiles]}


# ---- connections and drafts ----------------------------------------------------------------------------------------

def create_profile(actor, data) -> dict:
    provider = registry.get(data.kind, data.provider)
    if provider is None:
        raise ValidationFailed.field("provider", "Unknown provider for this kind of connection.")
    if data.purpose not in provider.purposes:
        raise ValidationFailed.field("purpose", f"Must be one of: {', '.join(provider.purposes)}.")
    if provider.app_profiles and current_app.config["SETTINGS"].profile not in provider.app_profiles:
        raise ValidationFailed.field("provider", f"{provider.id} is offered on the {', '.join(provider.app_profiles)} "
                                                 f"profile only.")
    session = context.session()
    taken = session.scalar(select(func.count()).select_from(SettingProfile).where(
        SettingProfile.kind == data.kind, func.lower(SettingProfile.name) == data.name.lower(),
        SettingProfile.archived_at.is_(None)))
    if taken:
        raise Conflict(f"A connection named {data.name} already exists.", code="DUPLICATE")
    now = context.now()
    profile = SettingProfile(kind=data.kind, provider=data.provider, name=data.name, description=data.description,
                             purpose=data.purpose, enabled=0)
    context.stamp_create(profile, actor, now)
    session.add(profile)
    session.flush()
    _new_draft(actor, profile, provider, {}, {}, "Created")
    audit_service.record(actor, "CREATE", profile, None, audit_service.snapshot(profile))
    session.commit()
    return get_profile(profile.id)


def _new_draft(actor, profile, provider, values: dict, tokens: dict, note: str | None) -> SettingRevision:
    session = context.session()
    number = (session.scalar(select(func.max(SettingRevision.revision_no)).where(
        SettingRevision.profile_id == profile.id)) or 0) + 1
    revision = SettingRevision(profile_id=profile.id, revision_no=number, state=DRAFT,
                               schema_version=provider.schema_version, fields_json=json.dumps(values, sort_keys=True),
                               secrets_json=json.dumps(tokens, sort_keys=True) if tokens else None,
                               fingerprint=_fingerprint(provider, values, tokens, number), note=note)
    context.stamp_create(revision, actor, context.now())
    session.add(revision)
    session.flush()
    audit_service.record(actor, "CREATE", revision, None, audit_service.snapshot(revision))
    return revision


def _secret_changes(provider, changes: dict, tokens: dict, profile_id: int, encrypt: bool) -> tuple[dict, bool]:
    """Apply keep / replace / clear to the saved tokens. Returns (tokens, any secret changed). With encrypt=False
    (an unsaved candidate under test) a replaced secret is kept in plain text in memory only, never saved."""
    out, changed = dict(tokens), False
    for name, change in changes.items():
        if name not in provider.secrets:
            raise ValidationFailed.field(f"secrets.{name}", "Unknown secret.")
        if change.action == "keep":
            continue
        if change.action == "clear":
            changed = changed or name in out
            out.pop(name, None)
            continue
        value = change.value or ""
        if not value.strip():
            raise ValidationFailed.field(f"secrets.{name}", "Type the new value, or keep the saved one.")
        if value.strip().lower() in _PLACEHOLDERS:
            raise ValidationFailed.field(f"secrets.{name}", "That is a placeholder, not the secret.")
        try:
            out[name] = (secretbox.encrypt(_keys(), value, config_service.secret_context(profile_id, name))
                         if encrypt else ("plain:", value))
        except secretbox.SecretUnavailable as exc:
            raise Conflict(str(exc), code="NO_SETTINGS_KEY") from None
        changed = True
    return out, changed


def save_draft(actor, profile_id: int, data) -> dict:
    session = context.session()
    profile = _profile(profile_id, for_update=True)
    provider = _provider(profile)
    values, problems = registry.validate(provider, data.fields, complete=False)
    problems = [p for p in problems if p["message"] != "Required."]
    if problems:
        raise ValidationFailed("Some settings are not valid.", [{"field": f"fields.{p['field']}", "message": p["message"]}
                                                                for p in problems])
    if any(c.action != "keep" for c in data.secrets.values()):
        require_recent_reauth()
    draft = _draft(profile)
    if draft is not None:
        if data.draft_version is None or data.draft_version != draft.version:
            raise Conflict("Someone else saved this draft meanwhile. Reload to see their changes.", code="STALE_VERSION")
    else:
        base_revision = _revision(profile.active_revision_id)
        draft = _new_draft(actor, profile, provider,
                           json.loads(base_revision.fields_json) if base_revision else {},
                           _tokens(base_revision), data.note)
    before = audit_service.snapshot(draft)
    tokens, _changed = _secret_changes(provider, data.secrets, _tokens(draft), profile.id, encrypt=True)
    draft.fields_json = json.dumps(values, sort_keys=True)
    draft.secrets_json = json.dumps(tokens, sort_keys=True) if tokens else None
    draft.fingerprint = _fingerprint(provider, values, tokens, draft.revision_no)
    draft.note = data.note
    context.stamp_update(draft, actor, context.now())
    profile_before = audit_service.snapshot(profile)
    if data.name and data.name != profile.name:
        profile.name = data.name
    if data.description is not None and data.description != profile.description:
        profile.description = data.description
    context.stamp_update(profile, actor, context.now())
    session.flush()
    audit_service.record(actor, "UPDATE", draft, before, audit_service.snapshot(draft))
    if audit_service.snapshot(profile) != profile_before:
        audit_service.record(actor, "UPDATE", profile, profile_before, audit_service.snapshot(profile))
    session.commit()
    return get_profile(profile.id)


def discard_draft(actor, profile_id: int, data) -> dict:
    session = context.session()
    profile = _profile(profile_id, for_update=True)
    draft = _draft(profile)
    if draft is None:
        raise Conflict("There is no draft to discard.", code="NO_DRAFT")
    if draft.version != data.version:
        raise Conflict("Someone else saved this draft meanwhile. Reload to see their changes.", code="STALE_VERSION")
    before = audit_service.snapshot(draft)
    draft.state = DISCARDED
    context.stamp_update(draft, actor, context.now())
    session.flush()
    audit_service.record(actor, "UPDATE", draft, before, audit_service.snapshot(draft), "Draft discarded")
    session.commit()
    return get_profile(profile.id)


# ---- tests ---------------------------------------------------------------------------------------------------------

def _account_role(username: str) -> dict | None:
    user = context.session().scalar(select(AppUser).where(func.lower(AppUser.username) == username.lower()))
    if user is None:
        return None
    role = context.session().scalar(select(AppRole).where(AppRole.code == user.role_code))
    return {"role": user.role_code, "roleLabel": role.name_en if role else user.role_code,
            "roleLabelAr": role.name_ar if role else user.role_code,
            "active": bool(user.active), "displayName": user.display_name,
            "canAdminister": bool(user.active) and PERM_ADMIN in user.permissions}


def _candidate_settings(profile, provider, values: dict, tokens: dict) -> dict:
    """The Settings values of a candidate (decrypting its saved secrets; plain ones from an unsaved candidate)."""
    secrets = {}
    for name, token in tokens.items():
        if isinstance(token, tuple):
            secrets[name] = token[1]
        else:
            secrets[name] = secretbox.decrypt(_keys(), token, config_service.secret_context(profile.id, name))
    ids = [int(i) for i in values.get("caCertIds", [])]
    pems = [c.pem for c in context.session().scalars(select(SettingCert).where(
        SettingCert.id.in_(ids or [0]), SettingCert.archived_at.is_(None)))]
    rules = tuple(egress.Rule(r.host, r.port, r.purpose) for r in context.session().scalars(
        select(EgressRule).where(EgressRule.archived_at.is_(None))))
    if provider.kind == "DATABASE":
        return database_provider.candidate(provider, values, secrets, pems, rules)
    return {**ldap_provider.settings_values(values, secrets, pems), "egress_rules": rules}


def run_test(actor, profile_id: int, data) -> dict:
    """Test the draft (default), the active revision, or unsaved candidate values. Never changes the configuration
    in use. Results are stored against the fingerprint they tested, so an edit makes them stale."""
    session = context.session()
    profile = _profile(profile_id)
    provider = _provider(profile)
    _rate_limit(actor, profile.id)
    revision = None
    if data.target == "candidate":
        candidate = data.candidate or None
        if candidate is None:
            raise ValidationFailed.field("candidate", "Send the values to test.")
        values, problems = registry.validate(provider, candidate.fields, complete=True)
        base_tokens = _tokens(_draft(profile) or _revision(profile.active_revision_id))
        tokens, _changed = _secret_changes(provider, candidate.secrets, base_tokens, profile.id, encrypt=False)
        ids = {n: (_secret_digest(t[1]) if isinstance(t, tuple) else t) for n, t in tokens.items()}
        fingerprint = _fingerprint(provider, values, ids)
    else:
        revision = _draft(profile) if data.target == "draft" else _revision(profile.active_revision_id)
        if revision is None:
            raise Conflict(f"There is no {data.target} revision to test.", code="NOTHING_TO_TEST")
        values, problems = registry.validate(provider, json.loads(revision.fields_json), complete=True)
        tokens, fingerprint = _tokens(revision), revision.fingerprint
    if problems:
        raise ValidationFailed("Complete the settings before testing.",
                               [{"field": f"fields.{p['field']}", "message": p["message"]} for p in problems])
    if any(s not in tokens for s in provider.required_secrets):
        raise ValidationFailed.field("secrets", "Save the required password before testing.")
    try:
        candidate_values = _candidate_settings(profile, provider, values, tokens)
    except secretbox.SecretUnavailable as exc:
        raise Conflict(str(exc), code="SECRET_UNAVAILABLE") from None
    sample = data.sample.model_dump() if data.sample else None
    base = current_app.config["SETTINGS"]
    session.rollback()  # end the read transaction: the stages wait on the network, holding no database lock
    if provider.kind == "DATABASE":
        results = database_provider.run_tests(provider, candidate_values, Base.metadata,
                                              database_provider.running_key(base))
    else:
        results = ldap_provider.run_tests(base, candidate_values, current_app.config.get("DIRECTORY_CONNECTION_FACTORY"),
                                          sample, _account_role_outside)
    now = context.now()
    for r in results:
        if r.outcome == "SKIPPED":
            continue
        code = r.code
        if r.stage == ldap_provider.SIGN_IN and r.outcome == "PASSED":
            # Who signed in: the method switch needs someone who can administer the app.
            admin = (r.detail or {}).get("appAccount", {}).get("canAdminister")
            code = SIGN_IN_ADMIN if admin else SIGN_IN_NOT_ADMIN
        session.add(SettingTest(profile_id=profile.id, revision_id=revision.id if revision else None,
                                fingerprint=fingerprint, stage=r.stage, outcome=r.outcome, code=code,
                                message=(r.message or "")[:500], latency_ms=r.latency_ms, tested_at=now,
                                tested_by=actor.id))
    session.commit()
    return {"target": data.target, "fingerprint": fingerprint[:12],
            "results": [{"stage": r.stage, "outcome": r.outcome, "code": r.code, "message": r.message,
                         "hint": r.hint, "latencyMs": r.latency_ms} for r in results],
            "profile": get_profile(profile.id)}


def _account_role_outside(username: str) -> dict | None:
    """The role preview during a test, read in its own short transaction (the test holds none)."""
    try:
        return _account_role(username)
    finally:
        context.session().rollback()


# ---- apply, enable, disable, delete, rollback -----------------------------------------------------------------------

def apply(actor, profile_id: int, data) -> dict:
    require_recent_reauth()
    session = context.session()
    profile = _profile(profile_id, for_update=True)
    provider = _provider(profile)
    context.check_version(profile, data.version)
    draft = _draft(profile)
    if draft is None or draft.version != data.draft_version:
        raise Conflict("The draft changed or is gone. Reload, test it again, then apply.", code="STALE_VERSION")
    blockers = _ready(provider, draft, _latest_tests(profile.id, draft.fingerprint))
    if blockers:
        messages = {"FUTURE": "This provider is configuration-only for now and cannot be activated.",
                    "INVALID": "Some settings are missing or not valid.",
                    "SECRET_MISSING": "A required secret is not saved.",
                    "NOT_TESTED": f"Test this exact draft (all required stages passing, within the last "
                                  f"{TEST_FRESH_MINUTES} minutes) before applying it."}
        raise Conflict(messages[blockers[0]], code=f"NOT_READY_{blockers[0]}")
    uses = _in_use(profile)
    if "SIGN_IN" in uses and not _signed_in_with(profile.id, draft.fingerprint):
        raise Conflict("This connection is the sign-in method: run a test sign-in as an active administrator with this "
                       "draft first, so nobody is locked out.", code="NEEDS_SIGN_IN_TEST")
    # Prove the candidate initialises (every secret decrypts, the values convert) before anything changes.
    try:
        _candidate_settings(profile, provider, json.loads(draft.fields_json), _tokens(draft))
    except (secretbox.SecretUnavailable, ValueError) as exc:
        raise Conflict(f"The draft cannot be used: {exc}", code="CANNOT_INITIALISE") from None
    now = context.now()
    old = _revision(profile.active_revision_id)
    if old is not None:
        before = audit_service.snapshot(old)
        old.state = SUPERSEDED
        context.stamp_update(old, actor, now)
        session.flush()
        audit_service.record(actor, "UPDATE", old, before, audit_service.snapshot(old), "Superseded")
    before = audit_service.snapshot(draft)
    draft.state = ACTIVE
    context.stamp_update(draft, actor, now)
    profile_before = audit_service.snapshot(profile)
    profile.active_revision_id = draft.id
    other_on = session.scalar(select(func.count()).select_from(SettingProfile).where(
        SettingProfile.kind == profile.kind, SettingProfile.purpose == profile.purpose, SettingProfile.id != profile.id,
        SettingProfile.enabled == 1, SettingProfile.archived_at.is_(None)))
    if old is None and not other_on and not provider.restart_required:
        profile.enabled = 1  # the first activation of the only connection for this purpose switches it on
    context.stamp_update(profile, actor, now)
    session.flush()
    note = "Staged for restart" if provider.restart_required else "Applied"
    audit_service.record(actor, "UPDATE", draft, before, audit_service.snapshot(draft), note)
    audit_service.record(actor, "UPDATE", profile, profile_before, audit_service.snapshot(profile), note)
    if not provider.restart_required:  # a staged database changes nothing in the running app
        _bump_generation(actor)
    session.commit()
    config_service.refresh()
    return get_profile(profile.id)


def _signed_in_with(profile_id: int, fingerprint: str) -> bool:
    """A fresh PASSED test sign-in, for this exact revision, by an active administrator."""
    fresh = context.now() - timedelta(minutes=TEST_FRESH_MINUTES)
    return context.session().scalar(select(func.count()).select_from(SettingTest).where(
        SettingTest.profile_id == profile_id, SettingTest.fingerprint == fingerprint,
        SettingTest.stage == ldap_provider.SIGN_IN, SettingTest.outcome == "PASSED", SettingTest.code == SIGN_IN_ADMIN,
        SettingTest.tested_at >= fresh)) > 0


def set_enabled(actor, profile_id: int, data, enabled: bool) -> dict:
    require_recent_reauth()
    session = context.session()
    profile = _profile(profile_id, for_update=True)
    if _provider(profile).restart_required:
        raise Conflict("A database connection has no switch: it is staged, then used after the planned restart.",
                       code="RESTART_PROVIDER")
    context.check_version(profile, data.version)
    if bool(profile.enabled) == enabled:
        return get_profile(profile.id)
    before = audit_service.snapshot(profile)
    if enabled:
        if profile.active_revision_id is None:
            raise Conflict("Apply a tested draft first.", code="NOT_ACTIVE")
        others = list(session.scalars(select(SettingProfile).where(
            SettingProfile.kind == profile.kind, SettingProfile.purpose == profile.purpose,
            SettingProfile.id != profile.id, SettingProfile.enabled == 1, SettingProfile.archived_at.is_(None))
            .with_for_update()))
        if any(_in_use(o) for o in others):
            active = _revision(profile.active_revision_id)
            if not _signed_in_with(profile.id, active.fingerprint):
                raise Conflict("Sign-in uses the directory now: run a test sign-in as an active administrator with this "
                               "connection first, then switch.", code="NEEDS_SIGN_IN_TEST")
        for other in others:  # one connection per purpose: switching this one on switches the other off
            other_before = audit_service.snapshot(other)
            other.enabled = 0
            context.stamp_update(other, actor, context.now())
            session.flush()
            audit_service.record(actor, "UPDATE", other, other_before, audit_service.snapshot(other),
                                 f"Replaced by {profile.name}")
    else:
        uses = _in_use(profile)
        if uses:
            raise Conflict("Sign-in uses this connection. Switch the sign-in method, or switch on another tested "
                           "connection, first.", code="IN_USE")
    profile.enabled = 1 if enabled else 0
    context.stamp_update(profile, actor, context.now())
    session.flush()
    audit_service.record(actor, "UPDATE", profile, before, audit_service.snapshot(profile),
                         "Enabled" if enabled else "Disabled")
    _bump_generation(actor)
    session.commit()
    config_service.refresh()
    return get_profile(profile.id)


def delete_profile(actor, profile_id: int, data) -> None:
    require_recent_reauth()
    session = context.session()
    profile = _profile(profile_id, for_update=True)
    context.check_version(profile, data.version)
    if profile.enabled:
        raise Conflict("Switch this connection off before deleting it.", code="IN_USE")
    if _in_use(profile):
        raise Conflict("The app runs on this database now; it cannot be deleted.", code="IN_USE")
    before = audit_service.snapshot(profile)
    profile.archived_at, profile.archived_by = context.now(), actor.id
    context.stamp_update(profile, actor, context.now())
    session.flush()
    audit_service.record(actor, "ARCHIVE", profile, before, audit_service.snapshot(profile), "Deleted")
    _bump_generation(actor)
    session.commit()
    config_service.refresh()


def rollback(actor, profile_id: int, data) -> dict:
    """A new draft with an older revision's values and secrets. It must be tested and applied like any draft (a
    secret may have expired or been revoked since)."""
    session = context.session()
    profile = _profile(profile_id, for_update=True)
    provider = _provider(profile)
    context.check_version(profile, data.version)
    source = _revision(data.revision_id)
    if source is None or source.profile_id != profile.id or source.state == DRAFT:
        raise NotFound("That revision was not found.")
    if _draft(profile) is not None:
        raise Conflict("Discard the current draft first.", code="DRAFT_EXISTS")
    _new_draft(actor, profile, provider, json.loads(source.fields_json), _tokens(source),
               f"Copy of revision {source.revision_no}")
    session.commit()
    return get_profile(profile.id)


# ---- the sign-in method --------------------------------------------------------------------------------------------

def break_glass_ready() -> bool:
    """The emergency administrator exists, is active and has a password set from the server (set-break-glass-password)."""
    name = current_app.config["SETTINGS"].break_glass_username
    if not name:
        return False
    user = context.session().scalar(select(AppUser).where(func.lower(AppUser.username) == name.lower()))
    if user is None or not user.active or PERM_ADMIN not in user.permissions:
        return False
    reasons = context.session().scalars(select(AuditEvent.reason).where(
        AuditEvent.entity_type == "APP_USER", AuditEvent.entity_id == user.id, AuditEvent.action == "UPDATE",
        AuditEvent.actor_id == user.id))
    return BREAK_GLASS_PASSWORD_NOTE in reasons


def sign_in_status() -> dict:
    method, source, row = _sign_in_method()
    base = current_app.config["SETTINGS"]
    live = context.session().scalar(select(SettingProfile).where(
        SettingProfile.kind == "LDAP", SettingProfile.enabled == 1, SettingProfile.archived_at.is_(None),
        SettingProfile.active_revision_id.is_not(None)))
    tested = bool(live and _signed_in_with(live.id, _revision(live.active_revision_id).fingerprint))
    return {"method": method, "source": source, "version": row.version if row else None,
            "options": list(SIGN_IN_METHODS), "directoryProfileId": str(live.id) if live else None,
            "directoryReady": tested,
            "breakGlass": {"username": base.break_glass_username, "ready": break_glass_ready()},
            "breakGlassRequired": not base.local_env,
            "envDirectory": bool(base.ldap_servers)}


def set_sign_in_method(actor, data) -> dict:
    require_recent_reauth()
    session = context.session()
    method, source, row = _sign_in_method()
    if row is not None and data.version != row.version:
        raise Conflict("Someone else changed the sign-in method meanwhile. Reload.", code="STALE_VERSION")
    if data.method == method and source == "SETTINGS":
        return sign_in_status()
    base = current_app.config["SETTINGS"]
    if data.method == "ldap":
        status = sign_in_status()
        if not status["directoryProfileId"]:
            raise Conflict("Apply and switch on a directory connection first.", code="NO_DIRECTORY")
        if not status["directoryReady"]:
            raise Conflict(f"Run a test sign-in as an active administrator on the directory connection (within the last "
                           f"{TEST_FRESH_MINUTES} minutes) first, so at least one administrator can sign in with it.",
                           code="NEEDS_SIGN_IN_TEST")
        if not base.local_env and not break_glass_ready():
            raise Conflict("Set up the emergency (break-glass) administrator on the server first (BREAK_GLASS_USERNAME "
                           "and flask set-break-glass-password): it is the way back in if the directory fails.",
                           code="NO_BREAK_GLASS")
    now = context.now()
    if row is None:
        session.add(ConnectionSetting(name=SIGN_IN_METHOD, value=data.method, updated_at=now, updated_by=actor.id))
    else:
        row.value, row.updated_at, row.updated_by = data.method, now, actor.id
    _audit_setting(actor, SIGN_IN_METHOD, method if source == "SETTINGS" else f"{method} (from the server file)",
                   data.method)
    _bump_generation(actor)
    session.commit()
    config_service.refresh()
    return sign_in_status()


# ---- certificates --------------------------------------------------------------------------------------------------

def _cert_dto(cert: SettingCert) -> dict:
    return {"id": str(cert.id), "name": cert.name, "sha256": cert.sha256, "subject": cert.subject,
            "issuer": cert.issuer, "notBefore": iso_utc(cert.not_before), "notAfter": iso_utc(cert.not_after),
            "state": certs.state(cert.not_after, context.now()), "version": cert.version,
            "usedBy": _cert_users(cert.id), "createdAt": iso_utc(cert.created_at)}


def _cert_users(cert_id: int) -> list[str]:
    users = []
    for profile in context.session().scalars(select(SettingProfile).where(SettingProfile.archived_at.is_(None))):
        for revision in (_revision(profile.active_revision_id), _draft(profile)):
            if revision and str(cert_id) in json.loads(revision.fields_json).get("caCertIds", []):
                users.append(profile.name)
                break
    return users


def list_certs() -> dict:
    return {"items": [_cert_dto(c) for c in context.session().scalars(
        select(SettingCert).where(SettingCert.archived_at.is_(None)).order_by(SettingCert.name))]}


def upload_cert(actor, name: str, data: bytes) -> dict:
    require_recent_reauth()  # a new trust anchor is a security change
    session = context.session()
    try:
        facts = certs.parse(data)
    except certs.CertificateProblem as exc:
        raise ValidationFailed.field("file", str(exc)) from None
    existing = session.scalar(select(SettingCert).where(SettingCert.sha256 == facts["sha256"]))
    if existing is not None and existing.archived_at is None:
        raise Conflict(f"This certificate is already saved as {existing.name}.", code="DUPLICATE")
    name = " ".join((name or "").split())[:80] or facts["subject"][:80]
    if len(name) < 2:
        raise ValidationFailed.field("name", "Give the certificate a name.")
    if existing is not None:  # an archived copy: bring it back
        before = audit_service.snapshot(existing)
        existing.archived_at = existing.archived_by = None
        existing.name = name
        context.stamp_update(existing, actor, context.now())
        cert = existing
        session.flush()
        audit_service.record(actor, "RESTORE", cert, before, audit_service.snapshot(cert))
    else:
        cert = SettingCert(name=name, pem=facts["pem"], sha256=facts["sha256"], subject=facts["subject"],
                           issuer=facts["issuer"], not_before=facts["not_before"], not_after=facts["not_after"])
        context.stamp_create(cert, actor, context.now())
        session.add(cert)
        session.flush()
        audit_service.record(actor, "CREATE", cert, None, audit_service.snapshot(cert))
    _bump_generation(actor)
    session.commit()
    config_service.refresh()
    out = _cert_dto(cert)
    out["warning"] = None if facts["is_ca"] else "This certificate is not marked as a CA; connections signed by " \
                                                 "the company CA need the CA certificate itself."
    return out


def archive_cert(actor, cert_id: int, data) -> None:
    require_recent_reauth()
    session = context.session()
    cert = session.get(SettingCert, cert_id)
    if cert is None or cert.archived_at is not None:
        raise NotFound(f"Certificate {cert_id} was not found.")
    context.check_version(cert, data.version)
    if _cert_users(cert.id):
        raise Conflict(f"In use by {', '.join(_cert_users(cert.id))}. Choose another certificate there first.",
                       code="IN_USE")
    before = audit_service.snapshot(cert)
    cert.archived_at, cert.archived_by = context.now(), actor.id
    context.stamp_update(cert, actor, context.now())
    session.flush()
    audit_service.record(actor, "ARCHIVE", cert, before, audit_service.snapshot(cert))
    _bump_generation(actor)
    session.commit()
    config_service.refresh()


# ---- approved destinations -----------------------------------------------------------------------------------------

def _rule_dto(rule: EgressRule) -> dict:
    return {"id": str(rule.id), "host": rule.host, "port": rule.port, "purpose": rule.purpose, "note": rule.note,
            "version": rule.version, "updatedAt": iso_utc(rule.updated_at), "updatedBy": _user_name(rule.updated_by)}


def list_rules() -> dict:
    return {"items": [_rule_dto(r) for r in context.session().scalars(
        select(EgressRule).where(EgressRule.archived_at.is_(None)).order_by(EgressRule.purpose, EgressRule.host))]}


def _check_rule(host: str, port: int, purpose: str, exclude_id: int | None = None) -> str:
    host = egress.normalise_host(host)
    if not egress.valid_rule_host(host):
        raise ValidationFailed.field("host", "A server name (dc01.company.local), *.company.local, or an IP address; "
                                             "no scheme, port or path.")
    try:
        import ipaddress

        address = ipaddress.ip_address(host)
        if address.is_link_local or address.is_multicast or address.is_unspecified or str(address) == "100.100.100.200":
            raise ValidationFailed.field("host", "The app never connects to link-local, metadata or multicast "
                                                 "addresses.")
    except ValueError:
        pass
    taken = context.session().scalar(select(func.count()).select_from(EgressRule).where(
        EgressRule.host == host, EgressRule.port == port, EgressRule.purpose == purpose,
        EgressRule.archived_at.is_(None), EgressRule.id != (exclude_id or 0)))
    if taken:
        raise Conflict(f"{host}:{port} is already approved for {purpose}.", code="DUPLICATE")
    return host


def create_rule(actor, data) -> dict:
    require_recent_reauth()  # a new destination widens where the server may connect
    session = context.session()
    host = _check_rule(data.host, data.port, data.purpose)
    rule = EgressRule(host=host, port=data.port, purpose=data.purpose, note=data.note)
    context.stamp_create(rule, actor, context.now())
    session.add(rule)
    session.flush()
    audit_service.record(actor, "CREATE", rule, None, audit_service.snapshot(rule))
    _bump_generation(actor)
    session.commit()
    config_service.refresh()
    return _rule_dto(rule)


def update_rule(actor, rule_id: int, data) -> dict:
    require_recent_reauth()
    session = context.session()
    rule = session.get(EgressRule, rule_id)
    if rule is None or rule.archived_at is not None:
        raise NotFound(f"Destination {rule_id} was not found.")
    context.check_version(rule, data.version)
    before = audit_service.snapshot(rule)
    host = data.host if data.host is not None else rule.host
    port = data.port if data.port is not None else rule.port
    purpose = data.purpose if data.purpose is not None else rule.purpose
    rule.host = _check_rule(host, port, purpose, exclude_id=rule.id)
    rule.port, rule.purpose = port, purpose
    if "note" in data.model_fields_set:
        rule.note = data.note
    context.stamp_update(rule, actor, context.now())
    session.flush()
    audit_service.record(actor, "UPDATE", rule, before, audit_service.snapshot(rule))
    _bump_generation(actor)
    session.commit()
    config_service.refresh()
    return _rule_dto(rule)


def archive_rule(actor, rule_id: int, data) -> None:
    require_recent_reauth()
    session = context.session()
    rule = session.get(EgressRule, rule_id)
    if rule is None or rule.archived_at is not None:
        raise NotFound(f"Destination {rule_id} was not found.")
    context.check_version(rule, data.version)
    before = audit_service.snapshot(rule)
    rule.archived_at, rule.archived_by = context.now(), actor.id
    context.stamp_update(rule, actor, context.now())
    session.flush()
    audit_service.record(actor, "ARCHIVE", rule, before, audit_service.snapshot(rule))
    _bump_generation(actor)
    session.commit()
    config_service.refresh()


# ---- overview, history, diagnostics, the database ------------------------------------------------------------------

def overview() -> dict:
    profiles = list_profiles(None)["items"]
    cert_items = list_certs()["items"]
    return {
        "signIn": sign_in_status(),
        "connections": {kind: [p for p in profiles if p["kind"] == kind] for kind in ("LDAP", "DATABASE")},
        "failures": [p for p in profiles if p["health"] in ("FAILED", "DEGRADED")],
        "pendingDrafts": [p for p in profiles if p["pendingDraft"]],
        "certificates": {"expired": [c for c in cert_items if c["state"] == "EXPIRED"],
                         "expiring": [c for c in cert_items if c["state"] == "EXPIRING"]},
        "settingsKey": {"configured": bool(_keys()), "keyId": secretbox.current_key_id(_keys())},
        "config": config_service.status(),
    }


CONNECTION_ENTITIES = ("SETTING_PROFILE", "SETTING_REVISION", "SETTING_CERT", "EGRESS_RULE", "CONNECTION_SETTING")


def history(page: int, size: int) -> dict:
    from ...schemas.common import page_envelope

    session = context.session()
    query = select(AuditEvent).where(AuditEvent.entity_type.in_(CONNECTION_ENTITIES))
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    rows = session.scalars(query.order_by(AuditEvent.occurred_at.desc(), AuditEvent.id.desc())
                           .offset(page * size).limit(size))
    items = []
    for e in rows:
        before = json.loads(e.before_json) if e.before_json else None
        after = json.loads(e.after_json) if e.after_json else None
        changed = sorted(k for k in set(before or {}) | set(after or {})
                         if (before or {}).get(k) != (after or {}).get(k) and k != "version")
        items.append({"id": str(e.id), "at": iso_utc(e.occurred_at), "actor": e.actor.display_name,
                      "action": e.action, "entityType": e.entity_type, "entityId": str(e.entity_id),
                      "name": (after or before or {}).get("name") or (after or before or {}).get("host"),
                      "changed": changed, "reason": e.reason})
    return page_envelope(items, page, size, total)


BOOTSTRAP = (
    ("APP_PROFILE", "Which database family: demo (SQLite) or oracle."),
    ("ORACLE_DSN / ORACLE_USER / ORACLE_PASSWORD / ORACLE_SCHEMA", "The main database: needed to load everything "
                                                                   "else, so never stored only in that database."),
    ("SETTINGS_KEY (or SETTINGS_KEY_FILE)", "Encrypts the passwords saved here; never stored in the database."),
    ("BREAK_GLASS_USERNAME", "The emergency administrator: the way in when the sign-in method fails."),
    ("APP_LISTEN / APP_THREADS / ORACLE_POOL_MAX", "Server capacity (a restart applies them)."),
    ("TRUSTED_PROXY_COUNT / SESSION_*", "Web server and session behaviour."),
)


def diagnostics() -> dict:
    base = current_app.config["SETTINGS"]
    status = config_service.status()
    row = context.session().get(ConnectionSetting, CONFIG_GENERATION)
    generation = int(row.value) if row is not None else 0
    cutoff = context.now() - timedelta(minutes=5)
    processes = [{"id": p.id, "generation": p.generation, "lastSeen": iso_utc(p.last_seen_at),
                  "current": p.generation == generation, "recent": p.last_seen_at >= cutoff}
                 for p in context.session().scalars(select(ProcessHeartbeat).order_by(ProcessHeartbeat.id))]
    recent = [p for p in processes if p["recent"]]
    return {
        "generation": generation,
        "thisProcess": status,
        "processes": processes,
        "rollout": "COMPLETE" if recent and all(p["current"] for p in recent) else ("PARTIAL" if recent else "UNKNOWN"),
        "sources": status["sources"],
        "settingsKey": {"configured": bool(_keys()), "keyId": secretbox.current_key_id(_keys()),
                        "previousKeys": max(0, len(_keys()) - 1)},
        "bootstrap": [{"name": n, "why": w} for n, w in BOOTSTRAP],
        "profile": base.profile, "environment": "local" if base.local_env else "server",
    }


def database_status() -> dict:
    """The running database (read-only, from .env) with its health and whether it holds the demo data, and the
    staged candidates."""
    base = current_app.config["SETTINGS"]
    running = database_provider.running(base, db.engine)
    profiles = [profile_dto(p) for p in context.session().scalars(select(SettingProfile).where(
        SettingProfile.kind == "DATABASE", SettingProfile.archived_at.is_(None)).order_by(SettingProfile.name))]
    running["matchesProfile"] = next((p["id"] for p in profiles if "MAIN_DATABASE" in p["inUse"]), None)
    offered = [p.id for p in registry.all_providers() if p.kind == "DATABASE"
               and (not p.app_profiles or base.profile in p.app_profiles)]
    return {"running": running, "providers": offered, "staged": [p for p in profiles if p["state"] == "STAGED"]}


# ---- importing ldap.env --------------------------------------------------------------------------------------------

IMPORT_NOTE = "Imported from ldap.env"


def import_env(actor) -> dict:
    """The directory settings of ldap.env as a DRAFT connection (idempotent: a second import returns the first), with
    its CA certificate and an approved destination per server. Nothing is activated: test it, then apply it. The secret
    goes straight from the server's environment into the encrypted draft; it is never shown."""
    require_recent_reauth()
    base = current_app.config["SETTINGS"]
    session = context.session()
    if not base.ldap_servers:
        raise Conflict("ldap.env has no directory settings to import (AUTH_MODE=ldap and LDAP_SERVER ...).",
                       code="NOTHING_TO_IMPORT")
    existing = session.scalar(select(SettingProfile).where(SettingProfile.kind == "LDAP",
                                                           SettingProfile.description == IMPORT_NOTE,
                                                           SettingProfile.archived_at.is_(None)))
    if existing is not None:
        return {"created": False, "profile": get_profile(existing.id)}
    cert_ids = []
    if base.ldap_ca_data:
        data = base.ldap_ca_data.encode("ascii") if isinstance(base.ldap_ca_data, str) else base.ldap_ca_data
        pem_blocks = [b for b in data.split(b"-----END CERTIFICATE-----") if b"-----BEGIN CERTIFICATE-----" in b]
        for block in pem_blocks or [data]:
            chunk = block + b"-----END CERTIFICATE-----\n" if pem_blocks else block
            facts = certs.parse(chunk)
            cert = session.scalar(select(SettingCert).where(SettingCert.sha256 == facts["sha256"]))
            if cert is None:
                cert = SettingCert(name=(facts["subject"] or "Company CA")[:80], pem=facts["pem"],
                                   sha256=facts["sha256"], subject=facts["subject"], issuer=facts["issuer"],
                                   not_before=facts["not_before"], not_after=facts["not_after"])
                context.stamp_create(cert, actor, context.now())
                session.add(cert)
                session.flush()
                audit_service.record(actor, "CREATE", cert, None, audit_service.snapshot(cert), IMPORT_NOTE)
            cert_ids.append(str(cert.id))
    for host in base.ldap_servers:
        if not session.scalar(select(func.count()).select_from(EgressRule).where(
                EgressRule.host == host.lower(), EgressRule.port == base.ldap_port, EgressRule.purpose == "LDAP",
                EgressRule.archived_at.is_(None))):
            rule = EgressRule(host=host.lower(), port=base.ldap_port, purpose="LDAP", note=IMPORT_NOTE)
            context.stamp_create(rule, actor, context.now())
            session.add(rule)
            session.flush()
            audit_service.record(actor, "CREATE", rule, None, audit_service.snapshot(rule), IMPORT_NOTE)
    profile = SettingProfile(kind="LDAP", provider="ldap", name="Company directory", description=IMPORT_NOTE,
                             purpose="SIGN_IN", enabled=0)
    context.stamp_create(profile, actor, context.now())
    session.add(profile)
    session.flush()
    audit_service.record(actor, "CREATE", profile, None, audit_service.snapshot(profile), IMPORT_NOTE)
    values = {"servers": list(base.ldap_servers), "port": base.ldap_port, "security": base.ldap_security,
              "caCertIds": cert_ids, "baseDn": base.ldap_base_dn, "bindDn": base.ldap_bind_dn,
              "usernamePattern": base.ldap_username_pattern, "usernameAttribute": base.ldap_username_attribute,
              "displayNameAttribute": base.ldap_display_name_attribute, "timeoutSeconds": base.ldap_timeout_seconds}
    values, _problems = registry.validate(ldap_provider.PROVIDER, values, complete=False)
    tokens = {}
    if base.ldap_bind_password:
        tokens["bindPassword"] = secretbox.encrypt(_keys(), base.ldap_bind_password,
                                                   config_service.secret_context(profile.id, "bindPassword"))
    _new_draft(actor, profile, ldap_provider.PROVIDER, values, tokens, IMPORT_NOTE)
    session.commit()
    return {"created": True, "profile": get_profile(profile.id)}


# ---- the server's command line: recovery and key rotation ----------------------------------------------------------
# These run on the server (flask settings-recover / settings-rotate-key), so they need no password typed again: whoever
# can run them already controls the server. Each is audited as the administrator named with --as.

def recover(actor, sign_in: str | None = None, disable_id: int | None = None) -> list[str]:
    """The way back when nobody can sign in, or a connection breaks the app: put the sign-in method back to app
    passwords, and/or switch a connection off, bypassing the website's guards on purpose."""
    session = context.session()
    done = []
    if sign_in is not None:
        if sign_in not in SIGN_IN_METHODS:
            raise ValidationFailed.field("sign-in", f"Must be one of: {', '.join(SIGN_IN_METHODS)}.")
        method, _source, row = _sign_in_method()
        if row is None:
            session.add(ConnectionSetting(name=SIGN_IN_METHOD, value=sign_in, updated_at=context.now(),
                                          updated_by=actor.id))
        else:
            row.value, row.updated_at, row.updated_by = sign_in, context.now(), actor.id
        _audit_setting(actor, SIGN_IN_METHOD, method, sign_in, "Recovery from the server command line")
        done.append(f"sign-in method set to {sign_in}")
    if disable_id is not None:
        profile = _profile(disable_id, for_update=True)
        before = audit_service.snapshot(profile)
        profile.enabled = 0
        context.stamp_update(profile, actor, context.now())
        session.flush()
        audit_service.record(actor, "UPDATE", profile, before, audit_service.snapshot(profile),
                             "Switched off from the server command line (recovery)")
        done.append(f"connection {profile.id} ({profile.name}) switched off")
    if done:
        _bump_generation(actor)
        session.commit()
    return done


def rotate_key(actor) -> int:
    """Re-encrypt every saved secret with the current SETTINGS_KEY (old tokens are read with SETTINGS_KEY_PREVIOUS).
    Afterwards SETTINGS_KEY_PREVIOUS can be removed. Values and fingerprints do not change, so tests stay valid."""
    keys = _keys()
    if not keys:
        raise Conflict("No SETTINGS_KEY is configured.", code="NO_SETTINGS_KEY")
    current = secretbox.key_id(keys[0])
    session = context.session()
    changed = 0
    for revision in session.scalars(select(SettingRevision).where(SettingRevision.secrets_json.is_not(None))):
        tokens = json.loads(revision.secrets_json)
        if all(secretbox.token_key_id(t) == current for t in tokens.values()):
            continue
        fresh = {}
        for name, token in tokens.items():
            context_text = config_service.secret_context(revision.profile_id, name)
            fresh[name] = (token if secretbox.token_key_id(token) == current
                           else secretbox.encrypt(keys, secretbox.decrypt(keys, token, context_text), context_text))
        revision.secrets_json = json.dumps(fresh, sort_keys=True)
        changed += 1
    if changed:
        session.add(AuditEvent(actor_id=actor.id, action="UPDATE", entity_type="CONNECTION_SETTING", entity_id=0,
                               occurred_at=context.now(), before_json=None,
                               after_json=json.dumps({"name": "SETTINGS_KEY", "value": f"key {current}"}),
                               reason=f"Secrets of {changed} revision(s) re-encrypted with the current key"))
        _bump_generation(actor)
    session.commit()
    return changed
