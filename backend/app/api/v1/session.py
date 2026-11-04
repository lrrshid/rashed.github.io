"""GET/POST/DELETE /session: current user, login, logout. GET /session/options: how to sign in (public)."""
from __future__ import annotations

from flask import current_app, g, jsonify, make_response, request

from ...schemas.common import ApiModel, Query, required_text
from ...schemas.dto import session_user
from ...security import auth
from . import body, bp, user


Username = required_text(1, 120)


class LoginRequest(ApiModel):
    username: Username
    password: str  # not trimmed or normalised


def _session_body(account, csrf_token: str) -> dict:
    settings = current_app.config["SETTINGS"]
    return {
        "user": session_user(account, auth.permissions(account), auth.department_scope(account)),
        "viewAs": g.view_as_role.code if getattr(g, "view_as_role", None) is not None else None,
        "csrfToken": csrf_token,
        "dataMode": settings.data_mode,
        "timezone": settings.timezone,
        "authMode": settings.auth_mode,
    }


def sign_in_options(settings) -> dict:
    """What the sign-in page needs before anyone is signed in. Nothing secret: no server names or settings."""
    return {
        "authMode": settings.auth_mode,
        "usernameHint": "Windows username, e.g. U12345" if settings.is_ldap else None,
        # The shared-password mock accounts exist only on a local demo; the sign-in page then lists them.
        "mockAccounts": settings.profile == "demo" and settings.local_env and not settings.is_ldap,
    }


@bp.get("/session")
def get_session():
    return jsonify(_session_body(user(), g.csrf_token))


@bp.get("/session/options")
@auth.public
def session_options():
    Query(request.args, set())
    return jsonify(sign_in_options(current_app.config["SETTINGS"]))


@bp.post("/session")
@auth.public
def login():
    data = LoginRequest.model_validate(body())
    account, token, csrf_token = auth.login(data.username, data.password)
    settings = current_app.config["SETTINGS"]
    response = make_response(jsonify(_session_body(account, csrf_token)))
    response.set_cookie(
        auth.COOKIE_NAME,
        token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="Strict",
        path="/",
        max_age=settings.session_absolute_hours * 3600,
    )
    return response


@bp.delete("/session")
def logout():
    auth.logout()
    response = make_response("", 204)
    response.delete_cookie(auth.COOKIE_NAME, path="/", samesite="Strict")
    return response
