"""The effective configuration: the start-up Settings (.env, ldap.env) with what Settings > connections manages laid
over them (ported from the Asset Availability project). Every reader of the running configuration goes through
effective() (context.settings(), security/auth.py, security/directory.py), so an applied change reaches sign-in and
the directory without a restart.

Source of truth, per setting:
- The sign-in method: CONNECTION_SETTING SIGN_IN_METHOD once Settings has saved one, else AUTH_MODE (ldap.env / .env).
- The directory: once any LDAP connection has had an active revision, Settings manages it for good: the enabled
  connection's active revision is used, and with none enabled the directory is off; ldap.env's LDAP_* values are
  never used again (a disabled or cleared connection does not come back from an old file). Before that, ldap.env is
  the legacy fallback, shown as such in the Settings page.
- Everything else (the database, SETTINGS_KEY, the break-glass name ...) is start-up only.

Several processes (the server and the command-line jobs): an apply raises CONNECTION_SETTING CONFIG_GENERATION in the
same transaction. Each process reads that number at most every CHECK_SECONDS and rebuilds when it changed, then writes a
PROCESS_HEARTBEAT row (which generation it runs), so the diagnostics can say whether every process has the change. If a
rebuild fails (a secret that no key can decrypt), the process keeps its last good configuration and the error is shown.
"""
from __future__ import annotations

import dataclasses
import json
import logging
import os
import socket
import threading
import time
from datetime import datetime, timedelta, timezone

from flask import current_app, has_request_context, request
from sqlalchemy import delete, select

from ...core import secretbox
from ...core.config import Settings
from ...core.database import reset_write_intent, set_write_intent, write_intended
from ...extensions import db
from ...models import ConnectionSetting, EgressRule, ProcessHeartbeat, SettingCert, SettingProfile, SettingRevision
from . import egress, ldap_provider

log = logging.getLogger("cpc.connections")

CHECK_SECONDS = 3
HEARTBEAT_SECONDS = 30
STALE_PROCESS_HOURS = 24
SIGN_IN_METHOD = "SIGN_IN_METHOD"
CONFIG_GENERATION = "CONFIG_GENERATION"
# The sign-in methods Settings offers, and the AUTH_MODE each one means (local = the app's own passwords).
SIGN_IN_METHODS = {"local": "local", "ldap": "ldap"}
PROCESS_ID = f"{socket.gethostname()[:60]}:{os.getpid()}"
_STARTED = time.time()


@dataclasses.dataclass
class _State:
    generation: int | None = None
    base: Settings | None = None      # the start-up settings the cached ones were built on
    settings: Settings | None = None
    checked: float = 0.0
    beat: float = 0.0
    error: str | None = None
    sources: dict = dataclasses.field(default_factory=dict)
    lock: threading.Lock = dataclasses.field(default_factory=threading.Lock)


def _state(app) -> _State:
    return app.extensions.setdefault("connections_state", _State())


def _read_generation(session) -> int:
    row = session.get(ConnectionSetting, CONFIG_GENERATION)
    return int(row.value) if row is not None else 0


def secret_context(profile_id: int, name: str) -> str:
    return f"profile {profile_id} {name}"


def decrypt_secrets(keys: tuple, profile_id: int, secrets_json: str | None) -> dict:
    tokens = json.loads(secrets_json) if secrets_json else {}
    return {name: secretbox.decrypt(keys, token, secret_context(profile_id, name)) for name, token in tokens.items()}


def _build(base: Settings, session) -> tuple[Settings, dict]:
    """The effective Settings and where each managed part came from."""
    overrides, sources = {}, {}
    method = session.get(ConnectionSetting, SIGN_IN_METHOD)
    if method is not None and method.value in SIGN_IN_METHODS:
        overrides["auth_mode"] = SIGN_IN_METHODS[method.value]
        sources["signIn"] = "SETTINGS"
    else:
        sources["signIn"] = "ENV"

    profiles = list(session.scalars(select(SettingProfile).where(SettingProfile.kind == "LDAP")
                                    .order_by(SettingProfile.id)))
    managed = any(p.active_revision_id is not None for p in profiles)
    if managed:
        sources["directory"] = "SETTINGS"
        rules = tuple(egress.Rule(r.host, r.port, r.purpose) for r in session.scalars(
            select(EgressRule).where(EgressRule.archived_at.is_(None))))
        live = next((p for p in profiles if p.enabled and p.archived_at is None and p.active_revision_id), None)
        # The directory's fields go back to their defaults first: nothing from ldap.env survives.
        blank = {f.name: f.default for f in dataclasses.fields(Settings) if f.name.startswith("ldap_")}
        overrides.update(blank, egress_rules=rules)
        if live is not None:
            revision = session.get(SettingRevision, live.active_revision_id)
            values = json.loads(revision.fields_json)
            secrets = decrypt_secrets(base.settings_keys, live.id, revision.secrets_json)
            cert_ids = [int(i) for i in values.get("caCertIds", [])]
            pems = [c.pem for c in session.scalars(select(SettingCert).where(
                SettingCert.id.in_(cert_ids or [0]), SettingCert.archived_at.is_(None)))]
            overrides.update(ldap_provider.settings_values(values, secrets, pems))
            sources["directoryProfile"] = live.id
    else:
        sources["directory"] = "ENV" if base.ldap_servers else "NONE"
    return (dataclasses.replace(base, **overrides) if overrides else base), sources


def _heartbeat(state: _State, generation: int) -> None:
    """Best effort: which generation this process runs. A failure here must never fail the request, and is not
    retried before HEARTBEAT_SECONDS (a busy database must not slow every request down)."""
    state.beat = time.monotonic()
    session = db.new_session()
    token = set_write_intent(True)
    try:
        now = current_app.config["CLOCK"].now()  # the app clock (tests freeze it)
        row = session.get(ProcessHeartbeat, PROCESS_ID)
        if row is None:
            session.add(ProcessHeartbeat(id=PROCESS_ID, generation=generation, last_seen_at=now,
                                         started_at=datetime.fromtimestamp(_STARTED, timezone.utc)))
        else:
            row.generation, row.last_seen_at = generation, now
        session.execute(delete(ProcessHeartbeat).where(
            ProcessHeartbeat.last_seen_at < now - timedelta(hours=STALE_PROCESS_HOURS)))
        session.commit()
    except Exception:  # noqa: BLE001 - diagnostics only
        session.rollback()
        log.debug("process heartbeat not written", exc_info=True)
    finally:
        reset_write_intent(token)
        session.close()


def effective(app=None) -> Settings:
    """The configuration to use now. Cheap: a cached object, re-validated against the database every few seconds."""
    app = app or current_app._get_current_object()
    base: Settings = app.config["SETTINGS"]
    state = _state(app)
    now = time.monotonic()
    if state.settings is not None and state.base is base and now - state.checked < CHECK_SECONDS:
        return state.settings
    with state.lock:
        if state.base is not base:  # the start-up settings were replaced (tests): build again
            state.settings, state.generation, state.base = None, None, base
        if state.settings is not None and time.monotonic() - state.checked < CHECK_SECONDS:
            return state.settings
        session = db.new_session()
        token = set_write_intent(False)
        try:
            generation = _read_generation(session)
            if generation != state.generation or state.settings is None:
                try:
                    built, sources = _build(base, session)
                    state.settings, state.sources, state.error = built, sources, None
                    state.generation = generation
                except Exception as exc:  # noqa: BLE001 - keep the last good configuration
                    state.error = f"{type(exc).__name__}: {exc}"[:300]
                    log.error("connection settings could not be applied; keeping the last good configuration",
                              extra={"fields": {"generation": generation, "error": state.error}})
                    if state.settings is None:
                        state.settings = base
            state.checked = time.monotonic()
        except Exception:  # noqa: BLE001 - the tables may not exist yet (start-up, a database being migrated)
            state.settings = state.settings or base
            state.checked = time.monotonic()
            return state.settings
        finally:
            session.rollback()
            reset_write_intent(token)
            session.close()
    # Only on a read request, and never while this context means to write: a command, a write request, or a read
    # that writes (write_intent()) may hold this database's write lock already, and the heartbeat writes on its own
    # connection (on SQLite it would wait for itself until the busy timeout).
    if (time.monotonic() - state.beat > HEARTBEAT_SECONDS and state.generation is not None and has_request_context()
            and request.method in ("GET", "HEAD") and not write_intended()):
        _heartbeat(state, state.generation)
    return state.settings


def refresh(app=None) -> Settings:
    """After this process applied a change: rebuild now instead of within CHECK_SECONDS."""
    app = app or current_app._get_current_object()
    state = _state(app)
    state.checked = 0.0
    state.beat = 0.0
    return effective(app)


def status(app=None) -> dict:
    app = app or current_app._get_current_object()
    state = _state(app)
    return {"generation": state.generation, "error": state.error, "sources": dict(state.sources),
            "process": PROCESS_ID}
