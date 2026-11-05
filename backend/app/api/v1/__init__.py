"""/api/v1 blueprint. Every request is authenticated, CSRF-checked (if it changes state) and role-checked
on the server, regardless of what the browser shows or hides."""
from __future__ import annotations

import json

from flask import Blueprint, current_app, g, jsonify, request

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ...core.database import set_write_intent
from ...exceptions import Forbidden, Unauthenticated, ValidationFailed
from ...extensions import db
from ...models import AppRole
from ...security import auth, csrf

bp = Blueprint("api_v1", __name__, url_prefix="/api/v1")

MUTATING = frozenset({"POST", "PUT", "PATCH", "DELETE"})


@bp.before_request
def _authenticate():
    view = current_app.view_functions.get(request.endpoint)
    if view is None:
        return None  # unknown route -> 404 handler
    if getattr(view, "is_public", False):
        g.current_user = None
    else:
        user = auth.load_current_user()
        if user is None:
            raise Unauthenticated("Please sign in.")
        g.current_user = user
        csrf.enforce()
        _apply_view_as(user)
    if request.method in MUTATING:
        # The request's main transaction starts with BEGIN IMMEDIATE on SQLite (see core/database.py).
        set_write_intent(True)
        if g.current_user is not None:
            # Permissions are checked against the user as they are now, inside that transaction (the read takes
            # the SQLite write lock, which the transaction keeps until it ends).
            g.current_user = auth.recheck_for_write(g.current_user)
    return None


def _apply_view_as(user) -> None:
    """X-View-As: <ROLE_CODE> (admin preview of another role). Only for users with the admin permission, and only on
    reads: a change is never made "as" someone else."""
    code = (request.headers.get("X-View-As") or "").strip().upper()
    g.view_as_role = None
    if not code or not auth.can_admin(user):
        return
    if request.method in MUTATING:
        raise Forbidden("The role preview is read-only. Leave the preview to make changes.", code="PREVIEW_READ_ONLY")
    session = db.new_session()
    try:
        role = session.scalar(select(AppRole).where(AppRole.code == code)
                              .options(selectinload(AppRole.permission_links)))
        if role is None:
            raise ValidationFailed.field("X-View-As", "Unknown role.")
        session.expunge(role)
        g.view_as_role = role
    finally:
        session.close()


@bp.teardown_request
def _clear_write_intent(_exc):
    set_write_intent(False)


def body() -> dict:
    if not request.is_json:
        raise ValidationFailed("Send a JSON body with Content-Type: application/json.")
    try:
        payload = request.get_json(silent=True)
    except RecursionError:  # absurdly deep nesting
        payload = None
    if not isinstance(payload, dict):
        raise ValidationFailed("Request body must be a JSON object.")
    # JSON can carry a lone UTF-16 surrogate escape, which is not valid text: the database driver would fail on it
    # (a 500). Refuse it here, once, for every route.
    try:
        json.dumps(payload, ensure_ascii=False).encode("utf-8")
    except (UnicodeEncodeError, RecursionError, ValueError):
        raise ValidationFailed("The request contains invalid characters (unpaired surrogates).") from None
    return payload


def created(payload: dict, location: str):
    response = jsonify(payload)
    response.status_code = 201
    response.headers["Location"] = location
    return response


def user():
    return auth.current_user()


# Route modules register themselves on `bp`.
from . import admin, capabilities, dashboard, documents_alerts, health, operations, projects, session, users  # noqa: E402,F401
