"""User tracking «تتبع المستخدمين» (permission tracking.view, never in a role preview): every action of every person,
carried out or refused (services/tracking_service.py). Read only: the log is append-only."""
from __future__ import annotations

from flask import jsonify, request

from ...schemas.common import Query
from ...security.auth import require_tracking
from ...services import tracking_service
from . import bp, user


@bp.get("/tracking/actions")
def tracking_actions():
    require_tracking(user())
    q = Query(request.args, {"from", "to", "user", "kind", "result", "q"})
    page, size = q.page()
    filters = {"from": q.date("from"), "to": q.date("to"), "user": q.id("user"),
               "kind": q.choice("kind", tuple(tracking_service.KINDS)), "result": q.choice("result", tracking_service.RESULTS),
               "q": q.text("q", 100)}
    return jsonify(tracking_service.actions(filters, page, size))


@bp.get("/tracking/actions/<int:action_id>")
def tracking_action(action_id: int):
    require_tracking(user())
    Query(request.args, set())
    return jsonify(tracking_service.action(action_id))


@bp.get("/tracking/users")
def tracking_users():
    require_tracking(user())
    q = Query(request.args, {"from", "to"})
    return jsonify(tracking_service.users(q.date("from"), q.date("to")))
