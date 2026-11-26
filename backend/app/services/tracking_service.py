"""User tracking «تتبع المستخدمين» (owner, 25 Nov 2026: the commander sees everything people do in the system; permission
tracking.view). record_request() runs after every API request (api/v1 after_request) and writes one ACTION_LOG row for
each action, carried out or refused: sign-in attempts and sign-outs, every change asked for (POST, PUT, PATCH,
DELETE), opening a record or a report, and every download or export. Lists, dashboards and look-ups are not actions.

What a row keeps: who (name and role as they were), what, on which record (its code and name), the outcome and, when it
failed, the error code, message and the names of the fields at fault, the date and time, the device (IP address) and
the request id. Never kept: passwords or any other value a request carries. Only the code of a record being added (or the
username of a person being added) is read from the request; a failed sign-in with a name that is no account keeps only
its first letters. A change that was carried out points at its audit row (the fields that changed, before and after)."""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, time, timedelta, timezone

from flask import g, request
from sqlalchemy import func, inspect as sa_inspect, or_, select

from ..core.clock import iso_utc
from ..core.database import reset_write_intent, set_write_intent
from ..exceptions import NotFound
from ..extensions import db
from ..models import ActionLog, AppRole, AppSession, AppUser, AuditEvent, Base
from ..schemas.common import page_envelope
from ..schemas.dto import sid
from . import audit_service, context

log = logging.getLogger("cpc.tracking")

MUTATING = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# Endpoints (api_v1.<name>) whose action is not read from the method: special steps, and the GET requests that are
# actions (opening a record or a report, downloads, exports). Every other GET is not tracked.
_ACTIONS = {
    "login": "SIGN_IN", "logout": "SIGN_OUT", "connections_reauth": "CONFIRM_PASSWORD",
    "attach_scan": "UPLOAD", "upload_version": "UPLOAD", "connections_upload_cert": "UPLOAD",
    "users_import": "IMPORT", "users_import_check": "CHECK_FILE", "connections_import_env": "IMPORT",
    "run_custom": "RUN_REPORT", "acknowledge_alerts": "ACKNOWLEDGE",
    "connections_test": "TEST", "connections_apply": "APPLY", "connections_enable": "ENABLE",
    "connections_disable": "DISABLE", "connections_rollback": "ROLLBACK", "connections_discard_draft": "DISCARD",
    "connections_archive_cert": "ARCHIVE", "connections_archive_rule": "ARCHIVE",
    "get_asset": "VIEW", "get_model": "VIEW", "get_requirement": "VIEW", "get_project": "VIEW", "get_document": "VIEW",
    "get_user": "VIEW", "run_report": "VIEW_REPORT",
    "export_assets": "EXPORT", "export_report": "EXPORT",
    "download_document": "DOWNLOAD", "scheduled_file": "DOWNLOAD", "users_import_template": "DOWNLOAD",
}
# The kinds the screen filters by.
KINDS = {
    "SESSION": ("SIGN_IN", "SIGN_OUT", "CONFIRM_PASSWORD"),
    "ADD": ("CREATE", "IMPORT"),
    "CHANGE": ("UPDATE", "APPLY", "ENABLE", "DISABLE", "ROLLBACK", "DISCARD", "TEST", "ACKNOWLEDGE"),
    "ARCHIVE": ("ARCHIVE", "RESTORE", "DELETE"),
    "FILES": ("UPLOAD", "DOWNLOAD", "EXPORT", "CHECK_FILE"),
    "VIEW": ("VIEW", "VIEW_REPORT", "RUN_REPORT"),
}
RESULTS = ("DONE", "FAILED")

# First part of the address -> the record type (the audit trail's names, so the screen words them the same way).
_RESOURCES = {
    "assets": "ASSET", "assets.csv": "ASSET", "models": "CAPABILITY_MODEL", "requirements": "CAPABILITY_REQUIREMENT",
    "projects": "PROJECT", "milestones": "MILESTONE", "risks": "RISK", "issues": "ISSUE", "tests": "TEST_EVENT",
    "maintenance": "MAINTENANCE_ORDER", "golden-samples": "GOLDEN_SAMPLE_TRIAL", "development": "DEVELOPMENT_OPPORTUNITY",
    "documents": "DOCUMENT", "users": "APP_USER", "settings": "APP_SETTING", "alert-rules": "ALERT_RULE",
    "alerts": "ALERT", "report-templates": "REPORT_TEMPLATE", "report-schedules": "REPORT_SCHEDULE", "reports": "REPORT",
    "saved-views": "SAVED_VIEW", "ai": "AI_LEVEL_CRITERION",
}
_CONNECTION_PARTS = {"profiles": "SETTING_PROFILE", "certificates": "SETTING_CERT", "destinations": "EGRESS_RULE",
                     "sign-in": "CONNECTION_SETTING", "import-env": "SETTING_PROFILE"}
# Record pages of the application a row can open.
_LINKS = {"ASSET": "/assets/{}", "CAPABILITY_MODEL": "/models/{}", "CAPABILITY_REQUIREMENT": "/requirements/{}",
          "PROJECT": "/projects/{}"}
_FILE_ENDPOINTS = ("attach_scan", "upload_version", "users_import", "users_import_check", "connections_upload_cert")
# Sign-in, sign-out and the password check: nothing of what they send is read as a record (a password may have been
# typed in the username box); a sign-in names its account through _sign_in_name() only.
_NO_TARGET = frozenset({"login", "logout", "connections_reauth"})
_USERNAME_LIKE = re.compile(r"^[A-Za-z0-9._@\\-]{1,120}$")
_MODELS: dict | None = None


def _clip(value, length: int):
    if value is None:
        return None
    text = " ".join(str(value).split())
    return text[:length] or None


def _model_of(entity_type: str | None):
    global _MODELS
    if _MODELS is None:
        _MODELS = {m.class_.__table__.name.upper(): m.class_ for m in Base.registry.mappers
                   if hasattr(m.class_, "__table__")}
    return _MODELS.get(entity_type) if entity_type else None


def _action_of(endpoint: str, method: str) -> str | None:
    if endpoint in _ACTIONS:
        return _ACTIONS[endpoint]
    if method not in MUTATING:
        return None
    if endpoint.startswith(("create_", "admin_create", "connections_create")):
        return "CREATE"
    if "archive" in endpoint:
        payload = request.get_json(silent=True)
        return "RESTORE" if isinstance(payload, dict) and payload.get("archived") is False else "ARCHIVE"
    if endpoint.startswith(("delete_", "connections_delete")):
        return "DELETE"
    return "UPDATE"


def _target(endpoint: str) -> tuple[str | None, int | None, str | None]:
    """(record type, record id, record code) from the address, the form of an upload, or the code of a record being
    added. Never any other value of the request."""
    if endpoint in _NO_TARGET:
        return None, None, None
    rule = request.url_rule.rule if request.url_rule is not None else request.path
    parts = rule.removeprefix("/api/v1/").split("/")
    args = request.view_args or {}
    ids = [v for v in args.values() if isinstance(v, int)]
    keys = [v for v in args.values() if isinstance(v, str)]
    head = parts[0]
    entity_id = ids[0] if ids else None
    code = None
    if endpoint == "attach_scan":
        kind = (request.form.get("entityType") or "").strip().upper()
        raw_id = (request.form.get("entityId") or "").strip()
        return (kind if _model_of(kind) else None), (int(raw_id) if raw_id.isdigit() else None), None
    if head == "admin":
        section = parts[1] if len(parts) > 1 else ""
        if section == "roles":
            entity_type = "APP_ROLE"
        elif section == "lists":
            from .admin_service import LISTS
            model = LISTS.get(args.get("kind"), (None,))[0]
            entity_type = model.__table__.name.upper() if model is not None else None
        elif section == "project-types":
            entity_type = "PROJECT_TYPE"
        else:
            entity_type = None
    elif head == "connections":
        entity_type = _CONNECTION_PARTS.get(parts[1] if len(parts) > 1 else "")
    elif head == "session":
        entity_type = None
    else:
        entity_type = _RESOURCES.get(head)
        code = keys[-1] if keys else None  # a setting's key, an alert type, a report's key
    if entity_id is None and code is None and request.method == "POST" and request.is_json:
        payload = request.get_json(silent=True)
        if isinstance(payload, dict):
            for key in ("code", "username"):
                if isinstance(payload.get(key), str) and payload[key].strip():
                    code = _clip(payload[key], 120)
                    break
    return entity_type, entity_id, code


def _record(entity_type: str | None, entity_id: int | None, code: str | None) -> tuple:
    """The record's code and names now (just after the action), or what the address said."""
    name_en = name_ar = None
    model = _model_of(entity_type)
    if model is not None and entity_id is not None:
        found = context.session().get(model, entity_id)
        if found is not None:
            code = (getattr(found, "code", None) or getattr(found, "username", None)
                    or getattr(found, "setting_key", None) or getattr(found, "alert_type", None) or code)
            for en, ar in (("name_en", "name_ar"), ("title_en", "title_ar"), ("display_name", "display_name")):
                if getattr(found, en, None):
                    name_en, name_ar = getattr(found, en), getattr(found, ar, None) or getattr(found, en)
                    break
    elif entity_type == "REPORT" and code:
        from .report_service import _cat
        report = _cat().get(code)
        if report:
            name_en, name_ar = report["titleEn"], report["titleAr"]
    return _clip(code, 120), _clip(name_en, 200), _clip(name_ar, 200)


def _detail(endpoint: str, response) -> str | None:
    """What else identifies the action: the name of the file sent or received, the format of an export."""
    if endpoint in _FILE_ENDPOINTS and response.status_code != 413:
        upload = request.files.get("file")
        name = upload.filename if upload is not None else None
        doc_type = request.form.get("docType")
        return _clip(f"{doc_type} · {name}" if doc_type and name else name, 300)
    found = re.search(r'filename="?([^";]+)"?', response.headers.get("Content-Disposition", ""))
    if found:
        return _clip(found.group(1), 300)
    if endpoint in ("run_report", "export_report") and request.args.get("format"):
        return _clip(request.args.get("format").upper(), 300)
    return None


def _sign_in_name() -> tuple[int | None, str, str | None, str | None]:
    """A sign-in attempt: (account id, username, display name, role) of the account named, if there is one. A name that
    is no account keeps only its first letters (it may be a password typed in the wrong box)."""
    from ..security.directory import normalise_username

    payload = request.get_json(silent=True) if request.is_json else None
    typed = payload.get("username") if isinstance(payload, dict) and isinstance(payload.get("username"), str) else ""
    typed = typed.strip()[:120]
    candidates = {typed.lower()}
    if context.settings().is_ldap and typed:
        candidates.add(normalise_username(typed).lower())
    account = None
    if typed:
        account = context.session().scalar(select(AppUser).where(func.lower(AppUser.username).in_(candidates)))
    if account is not None:
        return account.id, account.username, account.display_name, account.role_code
    shown = (typed[:3] + "***") if typed and _USERNAME_LIKE.match(typed) else "***"
    return None, shown, None, None


def record_request(response) -> None:
    """After an API request: one ACTION_LOG row if it was an action. Written in its own short transaction after the
    request's (whatever the request left unfinished is rolled back first, as the end of the request would)."""
    endpoint = (request.endpoint or "").rpartition(".")[2]
    if not endpoint:
        return
    action = _action_of(endpoint, request.method)
    if action is None:
        return
    status = response.status_code
    error = response.get_json(silent=True) if status >= 400 and response.is_json else None
    error = error if isinstance(error, dict) else {}
    if error.get("code") == "BUSY":
        return  # the database is locked by someone else: nothing can be written now
    person = g.get("tracking_user") or g.get("current_user")
    if person is None and action != "SIGN_IN":
        return  # no session (signed out, expired): nobody's action
    done = status < 400
    linked = []
    if done:
        for event, event_action, event_type, event_id in g.get("audit_events", []):
            identity = sa_inspect(event).identity
            if identity:
                linked.append((identity[0], event_action, event_type, event_id))
    entity_type, entity_id, code = _target(endpoint)
    detail = _detail(endpoint, response)
    fields = ",".join(sorted({str(f.get("field")) for f in error.get("fieldErrors") or [] if isinstance(f, dict)}))
    preview = getattr(g, "view_as_role", None)
    person_fields = None
    if person is not None:
        person_fields = (person.id, person.username, person.display_name, person.role_code)

    session = db.session()
    session.rollback()  # the request's transaction is over: a failed change is undone, a read is finished
    token = set_write_intent(True)
    try:
        if person_fields is None:
            person_fields = _sign_in_name()
        if linked:
            first_id, first_action, first_type, first_entity = linked[0]
            if entity_id is None or entity_type is None:
                entity_type, entity_id = first_type, first_entity
            if action in ("ARCHIVE", "RESTORE") and first_action in ("ARCHIVE", "RESTORE"):
                action = first_action
        record_code, name_en, name_ar = _record(entity_type, entity_id, code)
        user_id, username, display_name, role_code = person_fields
        session.add(ActionLog(
            occurred_at=context.now(), user_id=user_id, username=_clip(username, 120) or "***",
            display_name=_clip(display_name, 160), role_code=role_code, action=action,
            entity_type=entity_type, entity_id=entity_id, record_code=record_code, record_name_en=name_en,
            record_name_ar=name_ar, outcome="DONE" if done else "FAILED", http_status=status,
            error_code=_clip(error.get("code"), 40) if not done else None,
            error_message=_clip(error.get("message"), 300) if not done else None,
            error_fields=_clip(fields, 300) if not done else None, detail=detail,
            audit_event_id=linked[0][0] if linked else None, changes_count=len(linked),
            method=request.method, path=_clip(request.path, 300), client_ip=_clip(request.remote_addr, 64),
            request_id=_clip(g.get("request_id"), 64), preview_role=preview.code if preview is not None else None))
        session.commit()
    except Exception:
        session.rollback()
        log.exception("user tracking could not record an action",
                      extra={"fields": {"action": action, "path": request.path}})
    finally:
        reset_write_intent(token)


# ---------------------------------------------------------------- the screen

def _window(start: date | None, end: date | None) -> tuple[date, date, datetime, datetime]:
    """The chosen days (default: the last 7) and their UTC bounds, the days counted in the system's time zone."""
    today = context.today()
    end = end or today
    start = start or end - timedelta(days=6)
    if start > end:
        start, end = end, start
    zone = context.settings().zone
    low = datetime.combine(start, time.min, zone).astimezone(timezone.utc)
    high = datetime.combine(end + timedelta(days=1), time.min, zone).astimezone(timezone.utc)
    return start, end, low, high


def action_dto(a: ActionLog) -> dict:
    link = _LINKS.get(a.entity_type)
    return {
        "id": str(a.id), "occurredAt": iso_utc(a.occurred_at),
        "user": {"id": sid(a.user_id) if a.user_id is not None else None, "username": a.username,
                 "displayName": a.display_name, "role": a.role_code},
        "action": a.action, "entityType": a.entity_type,
        "entityId": sid(a.entity_id) if a.entity_id is not None else None,
        "record": {"code": a.record_code, "nameEn": a.record_name_en, "nameAr": a.record_name_ar},
        "link": link.format(a.entity_id) if link and a.entity_id is not None and a.action != "DELETE" else None,
        "outcome": a.outcome, "status": a.http_status, "errorCode": a.error_code, "errorMessage": a.error_message,
        "errorFields": a.error_fields.split(",") if a.error_fields else [], "detail": a.detail,
        "changesCount": a.changes_count, "ip": a.client_ip, "requestId": a.request_id, "method": a.method,
        "path": a.path, "previewRole": a.preview_role,
    }


def _where(f: dict, low: datetime, high: datetime):
    conditions = [ActionLog.occurred_at >= low, ActionLog.occurred_at < high]
    if f.get("user"):
        conditions.append(ActionLog.user_id == f["user"])
    if f.get("kind"):
        conditions.append(ActionLog.action.in_(KINDS[f["kind"]]))
    if f.get("result"):
        conditions.append(ActionLog.outcome == f["result"])
    if f.get("q"):
        like = f"%{f['q'].lower()}%"
        conditions.append(or_(func.lower(ActionLog.record_code).like(like), func.lower(ActionLog.record_name_en).like(like),
                              ActionLog.record_name_ar.like(f"%{f['q']}%"), func.lower(ActionLog.username).like(like),
                              func.lower(ActionLog.display_name).like(like)))
    return conditions


def actions(f: dict, page: int, size: int) -> dict:
    """The actions of the chosen days, newest first, with the totals of the chosen filters."""
    start, end, low, high = _window(f.get("from"), f.get("to"))
    session = context.session()
    conditions = _where(f, low, high)
    total = session.scalar(select(func.count()).select_from(ActionLog).where(*conditions))
    rows = session.scalars(select(ActionLog).where(*conditions)
                           .order_by(ActionLog.occurred_at.desc(), ActionLog.id.desc())
                           .offset(page * size).limit(size)).all()
    outcomes = dict(session.execute(select(ActionLog.outcome, func.count()).where(*conditions)
                                    .group_by(ActionLog.outcome)).all())
    failed_sign_ins = session.scalar(select(func.count()).select_from(ActionLog).where(
        *conditions, ActionLog.action == "SIGN_IN", ActionLog.outcome == "FAILED"))
    people = session.scalar(select(func.count(func.distinct(ActionLog.user_id))).where(*conditions))
    out = page_envelope([action_dto(a) for a in rows], page, size, total)
    out.update({"from": start.isoformat(), "to": end.isoformat(),
                "summary": {"total": total, "done": outcomes.get("DONE", 0), "failed": outcomes.get("FAILED", 0),
                            "failedSignIns": failed_sign_ins, "people": people}})
    return out


def action(action_id: int) -> dict:
    """One action with the fields its change moved (from the audit trail), when it was carried out."""
    row = context.session().get(ActionLog, action_id)
    if row is None:
        raise NotFound(f"Action {action_id} was not found.")
    out = action_dto(row)
    event = context.session().get(AuditEvent, row.audit_event_id) if row.audit_event_id is not None else None
    out["changes"] = audit_service.changes(event) if event is not None else []
    out["reason"] = event.reason if event is not None else None
    return out


def users(start: date | None, end: date | None) -> dict:
    """Everyone, with what they did in the chosen days: sign-ins (and failed ones), actions (and refused ones), the
    last action ever and whether they are signed in now."""
    start, end, low, high = _window(start, end)
    session = context.session()
    in_window = (ActionLog.occurred_at >= low) & (ActionLog.occurred_at < high) & ActionLog.user_id.is_not(None)
    counts: dict[int, dict] = {}
    for user_id, act, outcome, n in session.execute(
            select(ActionLog.user_id, ActionLog.action, ActionLog.outcome, func.count()).where(in_window)
            .group_by(ActionLog.user_id, ActionLog.action, ActionLog.outcome)):
        c = counts.setdefault(user_id, {"signIns": 0, "failedSignIns": 0, "actions": 0, "failed": 0})
        if act == "SIGN_IN":
            c["signIns" if outcome == "DONE" else "failedSignIns"] += n
        elif act != "SIGN_OUT":
            c["actions"] += n
            if outcome == "FAILED":
                c["failed"] += n
    last = dict(session.execute(select(ActionLog.user_id, func.max(ActionLog.occurred_at))
                                .where(ActionLog.user_id.is_not(None)).group_by(ActionLog.user_id)).all())
    idle = timedelta(minutes=context.settings().session_idle_minutes)
    online = {uid for (uid,) in session.execute(
        select(AppSession.user_id).where(AppSession.last_seen_at >= context.now() - idle))}
    roles = {r.code: r for r in session.scalars(select(AppRole))}
    items = []
    for u in session.scalars(select(AppUser).order_by(AppUser.display_name)):
        role = roles.get(u.role_code)
        c = counts.get(u.id, {"signIns": 0, "failedSignIns": 0, "actions": 0, "failed": 0})
        items.append({"id": str(u.id), "username": u.username, "displayName": u.display_name, "active": u.active,
                      "role": {"code": u.role_code, "nameEn": role.name_en if role else u.role_code,
                               "nameAr": role.name_ar if role else u.role_code},
                      **c, "online": u.id in online and u.active,
                      "lastActivity": iso_utc(last[u.id]) if last.get(u.id) else None})
    return {"from": start.isoformat(), "to": end.isoformat(), "items": items}
