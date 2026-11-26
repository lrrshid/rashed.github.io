"""Server-side sessions, login/logout, and role enforcement.

The cookie carries a random token; the database stores only its SHA-256 digest. Sessions rotate on login,
expire after idle and absolute limits, and are deleted on logout.
"""
from __future__ import annotations

import hashlib
import json
import logging
import secrets
from datetime import timedelta
from functools import wraps

from flask import current_app, g, request
from sqlalchemy import delete, func, select
from sqlalchemy.orm import selectinload
from werkzeug.security import check_password_hash, generate_password_hash

from ..core.database import reset_write_intent, set_write_intent, write_intent
from ..exceptions import (DirectoryUnavailable, Forbidden, NotFound, TooManyAttempts, Unauthenticated,
                          ValidationFailed)
from ..extensions import db
from ..models import AppSession, AppUser, AuditEvent
from ..models import ROLE_SYS_ADMIN
from . import csrf
from .directory import get_directory, normalise_username, password_can_be_sent

log = logging.getLogger("cpc.auth")

COOKIE_NAME = "cpc_sid"
_LAST_SEEN_THROTTLE = timedelta(seconds=60)
# Compared against when the username does not exist, so a miss costs the same time as a wrong password.
_DUMMY_HASH = generate_password_hash(secrets.token_hex(16))
# Audit reason of `flask set-break-glass-password` (user_service.set_break_glass_password). In ldap mode the
# break-glass account signs in only with a password that command set, never one set through Users & access.
BREAK_GLASS_PASSWORD_NOTE = "Break-glass password set"
# Audit reason when a directory sign-in brings a new display name (_take_directory_name).
DIRECTORY_NAME_NOTE = "Name updated from the company directory at sign-in"


def hash_password(password: str) -> str:
    return generate_password_hash(password)


def unusable_password_hash() -> str:
    """Hash of a random secret that is discarded at once: the account can never log in."""
    return generate_password_hash(secrets.token_urlsafe(48))


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _settings():
    """The configuration in effect: the server files with what Settings > connections manages laid over them (the
    sign-in method, the directory), so an applied change reaches sign-in without a restart."""
    from ..services.connections.config_service import effective  # the services import this module

    return effective()


def _clock():
    return current_app.config["CLOCK"]


def _client_ip() -> str:
    return request.remote_addr or "unknown"


def _check_local_password(username: str, password: str) -> int | None:
    """The user's id when `password` matches the stored hash and the account is active, else None."""
    # Check the password in a read-only transaction: the hash is deliberately slow (~0.1 s), and on SQLite a write
    # transaction (BEGIN IMMEDIATE) would block every other write for that long on each attempt, failed ones too.
    read = db.new_session()
    token_ro = set_write_intent(False)
    try:
        found = read.scalar(select(AppUser).where(AppUser.username == username))
        ok = check_password_hash(found.password_hash if found else _DUMMY_HASH, password)
        ok = ok and found is not None and bool(found.active)
        return found.id if ok else None
    finally:
        reset_write_intent(token_ro)
        read.close()


def _check_break_glass_password(name: str, password: str) -> int | None:
    """AUTH_MODE=ldap: the break-glass account's id when `password` matches, the account is an active SYS_ADMIN and its
    password was set by set-break-glass-password (an UPDATE it audited on itself, with BREAK_GLASS_PASSWORD_NOTE;
    the API never writes such a row for another account). Else None."""
    read = db.new_session()
    token_ro = set_write_intent(False)
    try:
        found = read.scalar(select(AppUser).where(func.lower(AppUser.username) == name.lower()))
        ok = check_password_hash(found.password_hash if found else _DUMMY_HASH, password)
        if not (ok and found is not None and found.active and found.role_code == ROLE_SYS_ADMIN):
            return None
        # The reason column is a CLOB on Oracle, which cannot be compared in SQL: compare the few rows here.
        reasons = read.scalars(select(AuditEvent.reason).where(
            AuditEvent.entity_type == "APP_USER", AuditEvent.entity_id == found.id, AuditEvent.action == "UPDATE",
            AuditEvent.actor_id == found.id))
        return found.id if BREAK_GLASS_PASSWORD_NOTE in reasons else None
    finally:
        reset_write_intent(token_ro)
        read.close()


def _active_user_id(username: str) -> int | None:
    """AUTH_MODE=ldap, after the directory accepted the password: the app account (any letter case), if active."""
    read = db.new_session()
    token_ro = set_write_intent(False)
    try:
        found = read.scalar(select(AppUser).where(func.lower(AppUser.username) == username.lower()))
        return found.id if found is not None and found.active else None
    finally:
        reset_write_intent(token_ro)
        read.close()


def _check_directory_sign_in(username: str, password: str, ip: str) -> tuple[int | None, str | None]:
    """AUTH_MODE=ldap. `username` is already normalised (U12345). Stored password hashes are ignored, except for the
    one break-glass account, whose password is checked here and never sent to the directory.
    Returns (user id or None, the person's display name in the directory or None: none for the break-glass account,
    nor when the directory entry has no display name). Raises DirectoryUnavailable when the directory cannot be asked."""
    settings = _settings()
    if settings.is_break_glass(username):
        user_id = _check_break_glass_password(settings.break_glass_username, password)
        log.warning("break-glass sign-in" if user_id else "break-glass sign-in failed",
                    extra={"fields": {"username": settings.break_glass_username, "clientIp": ip}})
        return user_id, None
    # A blank password, or one ldap3 cannot send (control characters...), is a wrong password: refused before the
    # directory is asked, so it is counted by the throttle like any other and never looks like an outage.
    if not password_can_be_sent(password) or not settings.username_matches_pattern(username):
        check_password_hash(_DUMMY_HASH, password)  # no directory call: spend about the same time anyway
        return None, None
    found = get_directory().authenticate(username, password)
    if found is None:
        return None, None
    # The directory gives the username itself when the entry has no display name: never a name to take.
    name = " ".join(found.display_name.split())
    if not name or name.upper() == found.username.upper():
        name = None
    # Option A (owner decision): only people an ADMIN added in Users & access, and still active, may come in.
    return _active_user_id(username), name


def _take_directory_name(session, user: AppUser, name: str, now) -> None:
    """AUTH_MODE=ldap (owner request 30 Oct 2026): a person's name follows the company directory. When the directory's
    display name differs from the app's, the sign-in takes it, in the sign-in's own transaction, audited as an UPDATE
    by the person (reason DIRECTORY_NAME_NOTE). The role and departments always stay the app's."""
    from ..services import audit_service  # the services import this module

    if user.display_name == name:
        return
    before = audit_service.snapshot(user)
    user.display_name = name
    user.updated_at = now
    session.flush()  # bumps the version, so the after-snapshot carries the one the user really has
    session.add(AuditEvent(actor_id=user.id, action="UPDATE", entity_type="APP_USER", entity_id=user.id,
                           occurred_at=now, before_json=json.dumps(before, sort_keys=True),
                           after_json=json.dumps(audit_service.snapshot(user), sort_keys=True),
                           reason=DIRECTORY_NAME_NOTE))


def login(username: str, password: str) -> tuple[AppUser, str, str]:
    """Verify credentials and open a new session. Returns (user, cookie_token, csrf_token)."""
    throttle = current_app.config["LOGIN_THROTTLE"]
    ip = _client_ip()
    ldap_mode = _settings().is_ldap
    # In ldap mode what people type is normalised (DOMAIN prefix and @domain dropped, uppercase), also for the throttle.
    key = normalise_username(username) if ldap_mode else username
    attempt = throttle.begin(ip, key)  # counted as a failure unless the sign-in succeeds
    if attempt is None:
        raise TooManyAttempts("Too many sign-in attempts. Wait a few minutes and try again.")

    directory_name = None
    if ldap_mode:
        try:
            user_id, directory_name = _check_directory_sign_in(key, password, ip)
        except DirectoryUnavailable as exc:
            throttle.cancel(ip, key, attempt)  # nobody's password was checked: not a failed attempt
            log.error("company directory unavailable at sign-in",
                      extra={"fields": {"username": key, "error": exc.detail, "hint": exc.hint}})
            raise
    else:
        user_id = _check_local_password(username, password)
    if user_id is None:
        raise Unauthenticated("Invalid username or password.", code="LOGIN_FAILED")

    session = db.new_session()
    try:
        with write_intent():
            # Re-read inside the write transaction: the account may have been deactivated in the meantime.
            user = session.scalar(
                select(AppUser).where(AppUser.id == user_id).options(*user_load_options()))
            if not (user and user.active):
                session.rollback()
                raise Unauthenticated("Invalid username or password.", code="LOGIN_FAILED")

            now = _clock().now()
            if directory_name:
                _take_directory_name(session, user, directory_name, now)
            old_token = request.cookies.get(COOKIE_NAME)
            if old_token:
                session.execute(delete(AppSession).where(AppSession.id == _digest(old_token)))
            idle_cutoff = now - timedelta(minutes=_settings().session_idle_minutes)
            session.execute(
                delete(AppSession).where(AppSession.user_id == user.id, AppSession.last_seen_at < idle_cutoff)
            )
            token = secrets.token_urlsafe(32)
            csrf_token = csrf.new_token()
            session.add(AppSession(id=_digest(token), user_id=user.id, csrf_token=csrf_token, created_at=now, last_seen_at=now))
            # The audit trail keeps who signed in and when (user tracking keeps every attempt); no values are recorded.
            session.add(AuditEvent(actor_id=user.id, action="SIGN_IN", entity_type="APP_USER", entity_id=user.id,
                                   occurred_at=now))
            session.commit()
            throttle.succeeded(ip, key, attempt)
            return user, token, csrf_token
    finally:
        session.close()


REAUTH_MINUTES = 10


def reauthenticate(user: AppUser, password: str) -> None:
    """POST /connections/reauth: check `password` for the signed-in person, the same way sign-in would (the directory,
    the break-glass account or a local password, by the method in effect), throttled like sign-in, and remember the
    moment on this session. Sensitive Settings steps then need it within REAUTH_MINUTES (require_recent_reauth)."""
    throttle = current_app.config["LOGIN_THROTTLE"]
    ip = _client_ip()
    key = f"reauth:{user.id}"
    attempt = throttle.begin(ip, key)
    if attempt is None:
        raise TooManyAttempts("Too many attempts. Wait a few minutes and try again.")
    if _settings().is_ldap:
        try:
            user_id, _name = _check_directory_sign_in(normalise_username(user.username), password, ip)
        except DirectoryUnavailable:
            throttle.cancel(ip, key, attempt)
            raise
    else:
        user_id = _check_local_password(user.username, password)
    if user_id != user.id:
        log.warning("settings password check failed", extra={"fields": {"userId": user.id, "clientIp": ip}})
        # 400 on the field, not 401: the page must not take a mistyped password for a lost session.
        raise ValidationFailed.field("password", "The password is not right.")
    token = request.cookies.get(COOKIE_NAME)
    session = db.session()
    row = session.get(AppSession, _digest(token)) if token else None
    if row is None:
        raise Unauthenticated("Please sign in again.")
    row.reauth_at = _clock().now()
    session.commit()
    throttle.succeeded(ip, key, attempt)


def require_recent_reauth() -> None:
    """A sensitive Settings step (apply, switch on or off, delete, a secret, the sign-in method, a certificate, a
    destination): the password must have been typed again on this session within REAUTH_MINUTES, else 403
    REAUTH_REQUIRED (the page asks for it, then tries once more)."""
    token = request.cookies.get(COOKIE_NAME)
    row = db.session().get(AppSession, _digest(token)) if token else None
    if row is None or row.reauth_at is None or _clock().now() - row.reauth_at > timedelta(minutes=REAUTH_MINUTES):
        raise Forbidden("Type your password again to confirm this change.", code="REAUTH_REQUIRED")


def logout() -> None:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return
    # The request's own session: DELETE /session already holds its write transaction (recheck_for_write), and a
    # second connection would wait for that lock.
    session = db.session()
    row = session.get(AppSession, _digest(token))
    if row is not None:
        session.add(AuditEvent(actor_id=row.user_id, action="SIGN_OUT", entity_type="APP_USER", entity_id=row.user_id,
                               occurred_at=_clock().now()))
    session.execute(delete(AppSession).where(AppSession.id == _digest(token)))
    session.commit()


def load_current_user() -> AppUser | None:
    """Resolve the session cookie in its own short transaction (kept separate from the request's
    main transaction so write requests can start theirs with BEGIN IMMEDIATE)."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    settings = _settings()
    now = _clock().now()
    session = db.new_session()
    try:
        row = session.get(AppSession, _digest(token))
        if row is None:
            session.rollback()
            return None
        # The user's role, permissions and departments are loaded now: the user is detached below and every check reads them.
        user = session.scalars(
            select(AppUser).where(AppUser.id == row.user_id).options(*user_load_options())
        ).one_or_none()
        expired = (
            now - row.last_seen_at > timedelta(minutes=settings.session_idle_minutes)
            or now - row.created_at > timedelta(hours=settings.session_absolute_hours)
            or user is None
            or not user.active
        )
        needs_touch = expired or now - row.last_seen_at > _LAST_SEEN_THROTTLE
        csrf_token = row.csrf_token
        if user is not None:
            session.expunge(user)  # keep its loaded attributes; the rollback below would expire them
        session.rollback()  # end the read transaction before any write
        if needs_touch:
            with write_intent():
                fresh = session.get(AppSession, _digest(token))
                if fresh is not None:
                    if expired:
                        session.delete(fresh)
                    else:
                        fresh.last_seen_at = now
                session.commit()
        if expired:
            return None
        g.csrf_token = csrf_token
        return user
    finally:
        session.close()


def recheck_for_write(user: AppUser) -> AppUser:
    """For a request that changes data: read the session and the user again inside the request's own transaction
    (on SQLite this first statement takes the write lock, BEGIN IMMEDIATE). load_current_user() answered from an
    earlier, separate transaction; a request that then waited behind an ADMIN's write must not go ahead with
    permissions the ADMIN has just removed (deactivated, role changed, department taken away).
    Returns the fresh user, attached to the request's session."""
    session = db.session()
    token = request.cookies.get(COOKIE_NAME)
    still_signed_in = token is not None and session.get(AppSession, _digest(token)) is not None
    fresh = session.scalars(
        select(AppUser).where(AppUser.id == user.id).options(*user_load_options())
    ).one_or_none()
    if not (still_signed_in and fresh is not None and fresh.active):
        raise Unauthenticated("Please sign in.")
    # Detached, like the user load_current_user() returns: if the request's transaction fails and rolls back,
    # the session expires its objects, and the error response and access log must still read the actor's id.
    session.expunge(fresh)
    return fresh


def current_user() -> AppUser:
    user = getattr(g, "current_user", None)
    if user is None:
        raise Unauthenticated("Please sign in.")
    return user


def user_load_options() -> tuple:
    """Eager loads every permission check needs, so a detached user still answers them."""
    from ..models import AppRole

    return (selectinload(AppUser.department_links),
            selectinload(AppUser.role).selectinload(AppRole.permission_links))


# ---- what each role may do ------------------------------------------------------------------------------------
# Every permission rule lives here; routes and services ask these functions instead of comparing role strings.
# Roles and their permissions are data (APP_ROLE, ROLE_PERMISSION), editable by a SYS_ADMIN in Settings > Roles.
# A role's scope is ALL (every department) or DEPARTMENT (only the departments in USER_DEPARTMENT).
# Records outside a user's scope answer 404, so their existence is not revealed.
#
# "View as" (admin preview): a user with the `admin` permission may send X-View-As: <ROLE_CODE> on GET requests
# to see the app as that role would (permissions of that role, every department). Writes are never previewed.

PERM_VIEW = "view"
PERM_EDIT_REQUIREMENTS = "edit.requirements"
PERM_EDIT_MODELS = "edit.models"
PERM_EDIT_ASSETS = "edit.assets"
PERM_EDIT_PROJECTS = "edit.projects"
PERM_EDIT_RISKS = "edit.risks"
PERM_EDIT_MAINTENANCE = "edit.maintenance"
PERM_EDIT_TESTING = "edit.testing"
PERM_EDIT_DOCUMENTS = "edit.documents"
# The edit.* permissions let a role add records of that kind; changing, archiving or restoring a record that exists
# also needs records.change (owner, 25 Nov 2026: the project manager and the user "add and view" only).
PERM_CHANGE = "records.change"
PERM_REPORTS_VIEW = "reports.view"
PERM_REPORTS_EXEC = "reports.exec"
PERM_REPORTS_BUILD = "reports.build"
PERM_REPORTS_SCHEDULE = "reports.schedule"
PERM_EXPORT = "export"
# The user tracking screen «تتبع المستخدمين» (services/tracking_service.py): every action of every person.
PERM_TRACKING = "tracking.view"
PERM_ADMIN = "admin"
PERMISSIONS = (PERM_VIEW, PERM_EDIT_REQUIREMENTS, PERM_EDIT_MODELS, PERM_EDIT_ASSETS, PERM_EDIT_PROJECTS,
               PERM_EDIT_RISKS, PERM_EDIT_MAINTENANCE, PERM_EDIT_TESTING, PERM_EDIT_DOCUMENTS, PERM_CHANGE,
               PERM_REPORTS_VIEW, PERM_REPORTS_EXEC, PERM_REPORTS_BUILD, PERM_REPORTS_SCHEDULE, PERM_EXPORT, PERM_TRACKING,
               PERM_ADMIN)

SCOPE_ALL = "ALL"
SCOPE_DEPARTMENT = "DEPARTMENT"
#: Department scope meaning "every department".
ALL_DEPARTMENTS = None


def _preview_role():
    """The role an admin is previewing on this request (X-View-As, GET only), else None."""
    return getattr(g, "view_as_role", None)


def permissions(user: AppUser) -> frozenset[str]:
    preview = _preview_role()
    if preview is not None:
        return preview.permissions
    return user.permissions


def has_permission(user: AppUser, permission: str) -> bool:
    return permission in permissions(user)


def can_admin(user: AppUser) -> bool:
    """Settings, lists, workflows, business rules, roles, users and the audit history. Never previewed."""
    return PERM_ADMIN in user.permissions and _preview_role() is None


def can_track(user: AppUser) -> bool:
    """User tracking: what every person did. The real role only: never in a role preview."""
    return PERM_TRACKING in user.permissions and _preview_role() is None


def require_tracking(user: AppUser) -> None:
    if not can_track(user):
        raise Forbidden("Only the commander and the roles given user tracking can see it.")


def department_scope(user: AppUser) -> frozenset[int] | None:
    """The departments the user may see: None means every department, otherwise exactly these ids."""
    if _preview_role() is not None:
        return ALL_DEPARTMENTS
    if user.role is not None and user.role.scope == SCOPE_DEPARTMENT:
        return user.department_ids
    return ALL_DEPARTMENTS


def can_access_department(user: AppUser, department_id: int | None) -> bool:
    scope = department_scope(user)
    return scope is ALL_DEPARTMENTS or (department_id is not None and department_id in scope)


def require_department_access(user: AppUser, department_id: int | None, what: str) -> None:
    """Out-of-scope records are reported as 'not found' so their existence is not revealed."""
    if not can_access_department(user, department_id):
        raise NotFound(what)


def require_permission(user: AppUser, permission: str) -> None:
    if not has_permission(user, permission):
        raise Forbidden("Your role does not allow that.", code="FORBIDDEN")


def require_edit(user: AppUser, permission: str, department_id: int | None = None) -> None:
    """A write (adding a record, or the first step of any change): the permission, the department in scope (when the
    record has one), and never during a preview."""
    if _preview_role() is not None:
        raise Forbidden("The role preview is read-only.", code="PREVIEW_READ_ONLY")
    require_permission(user, permission)
    if department_id is not None and not can_access_department(user, department_id):
        raise NotFound("That record was not found.")


def can_change(user: AppUser) -> bool:
    """Whether the role may change, archive and restore records that exist (not only add them)."""
    return has_permission(user, PERM_CHANGE)


def require_change(user: AppUser, permission: str, department_id: int | None = None) -> None:
    """Changing, archiving or restoring a record that exists. For the record permissions (edit.*) the role also needs
    records.change: without it, it adds records and views them only (403 ADD_ONLY). Out-of-scope records still answer
    404 first. Other writes through crud (settings, report templates, schedules) are governed by their own permission."""
    require_edit(user, permission, department_id)
    if permission.startswith("edit.") and not can_change(user):
        raise Forbidden("Your role may add records and view them, not change or archive them.", code="ADD_ONLY")


def require_admin(user: AppUser) -> None:
    if not can_admin(user):
        raise Forbidden("Only a system administrator can do that.")


def public(view):
    """Mark an /api view as reachable without a session."""
    view.is_public = True
    return view


def admin_only(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        require_admin(current_user())
        return view(*args, **kwargs)

    return wrapper


def permission_required(permission: str):
    def decorate(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            require_permission(current_user(), permission)
            return view(*args, **kwargs)

        return wrapper

    return decorate
