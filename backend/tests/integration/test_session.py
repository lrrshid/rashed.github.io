"""Login, logout, session rotation, idle/absolute expiry, CSRF and the login throttle (AUTH_MODE=local)."""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pytest

from app.extensions import db
from app.security.mock_credentials import MOCK_PASSWORD
from tests.conftest import Api, _app_from

COOKIE = "cpc_sid"
SESSION = "/api/v1/session"
ASSETS = "/api/v1/assets"
REQUIREMENT = "/api/v1/requirements/1"
LOGIN_FAILED_MESSAGE = "Invalid username or password."

ADMIN = "mock.admin"
ADMIN_NAME = "Mock System Administrator"
EXEC = "mock.exec"


# --------------------------------------------------------------------------- helpers

@pytest.fixture
def clock(app):
    """The app's FixedClock (conftest gives every app its own)."""
    return app.config["CLOCK"]


def _set_cookie_headers(res) -> list[str]:
    return [v for k, v in res.headers.items() if k.lower() == "set-cookie"]


def _session_cookie_header(res) -> str:
    headers = [h for h in _set_cookie_headers(res) if h.startswith(f"{COOKIE}=")]
    assert len(headers) == 1, _set_cookie_headers(res)
    return headers[0]


def _cookie_value(res) -> str:
    return _session_cookie_header(res).split(";", 1)[0].split("=", 1)[1]


def _client_with_cookie(app, value: str):
    client = app.test_client()
    client.set_cookie(COOKIE, value)
    return client


def _login(client, username, password=MOCK_PASSWORD, headers=None):
    return client.post(SESSION, json={"username": username, "password": password}, headers=headers or {})


def _db_path(app) -> Path:
    return Path(app.config["SETTINGS"].database_url.removeprefix("sqlite:///"))


def _sql(app, statement: str, params=()):
    con = sqlite3.connect(_db_path(app))
    try:
        con.execute(statement, params)
        con.commit()
    finally:
        con.close()


def _assert_error(res, status: int, code: str):
    assert res.status_code == status, (res.status_code, res.get_json())
    assert res.is_json
    payload = res.get_json()
    assert set(payload) == {"code", "message", "fieldErrors", "requestId"}
    assert payload["code"] == code
    return payload


def _ok(api: Api, url: str):
    res = api.get(url)
    assert res.status_code == 200, (res.status_code, res.get_json(silent=True))
    return res.get_json()


def _note(text: str) -> dict:
    """A small change any SYS_ADMIN may make (a requirement's notes)."""
    return {"notes": text, "reason": "Session test"}


# --------------------------------------------------------------------------- login

def test_login_success_returns_token_user_and_data_mode(anon):
    res = _login(anon.client, ADMIN)
    assert res.status_code == 200
    data = res.get_json()
    assert re.fullmatch(r"[0-9a-f]{32,}", data["csrfToken"])
    assert data["dataMode"] == "demo" and data["authMode"] == "local"
    user = data["user"]
    assert user["username"] == ADMIN
    assert user["displayName"] == ADMIN_NAME
    assert user["role"] == "SYS_ADMIN"
    assert user["roleName"]["en"] == "System administrator"
    assert user["departmentIds"] is None  # ALL-scoped: every department
    assert "admin" in user["permissions"]
    assert isinstance(user["id"], str)
    assert "passwordHash" not in user and "password" not in user


def test_login_as_executive_reports_executive_role(anon):
    res = _login(anon.client, EXEC)
    assert res.status_code == 200
    user = res.get_json()["user"]
    assert user["role"] == "EXECUTIVE" and "admin" not in user["permissions"]


def test_login_reports_role_and_departments_of_every_kind_of_user(app):
    """The browser learns the role and, for a department-scoped user, which departments it covers (ids are strings)."""
    capability = Api(app, "mock.capability").user
    assert (capability["role"], capability["departmentIds"]) == ("CAPABILITY_MGR", None)
    head = Api(app, "mock.head").user
    assert head["role"] == "DEPT_HEAD"
    assert head["departmentIds"] == ["2"]  # Group 2 only
    viewer = Api(app, "mock.viewer").user
    assert viewer["role"] == "VIEWER" and viewer["permissions"] == ["reports.view", "view"]


def test_login_works_without_csrf_header(app):
    client = app.test_client()
    res = client.post(SESSION, json={"username": ADMIN, "password": MOCK_PASSWORD})
    assert res.status_code == 200
    assert client.get(SESSION).status_code == 200


def test_session_cookie_is_httponly_samesite_and_path_root(anon):
    header = _session_cookie_header(_login(anon.client, ADMIN))
    attrs = [a.strip().lower() for a in header.split(";")]
    assert "httponly" in attrs
    assert any(a in ("samesite=strict", "samesite=lax") for a in attrs)
    assert "path=/" in attrs
    # The cookie carries a random token, never the user id or name.
    value = header.split(";", 1)[0].split("=", 1)[1]
    assert len(value) >= 32
    assert ADMIN not in value


def test_session_cookie_secure_flag_when_configured(seeded_template, tmp_path):
    secure_app = _app_from(seeded_template, tmp_path, cookie_secure=True)
    try:
        res = _login(secure_app.test_client(), ADMIN)
        assert res.status_code == 200
        attrs = [a.strip().lower() for a in _session_cookie_header(res).split(";")]
        assert "secure" in attrs
    finally:
        db.dispose()


def test_get_session_returns_same_body_and_token_as_login(admin):
    data = _ok(admin, SESSION)
    assert data["csrfToken"] == admin.csrf
    assert data["user"] == admin.user
    assert data["dataMode"] == "demo"


@pytest.mark.parametrize(
    "username,password",
    [
        (ADMIN, "wrong-password-1"),  # wrong password
        ("no.such.user", "whatever-123"),  # unknown user
        ("mock.viewer", "not-the-mock-password"),  # a real account, wrong password
        ("mock.viewer", ""),  # a real account, empty password
    ],
)
def test_login_failures_are_generic(anon, username, password):
    res = _login(anon.client, username, password)
    payload = _assert_error(res, 401, "LOGIN_FAILED")
    assert payload["message"] == LOGIN_FAILED_MESSAGE
    assert payload["fieldErrors"] == []
    assert _set_cookie_headers(res) == []


def test_login_failure_bodies_are_identical_except_request_id(app):
    bodies = []
    for username in (ADMIN, "no.such.user", "mock.viewer"):
        res = _login(app.test_client(), username, "wrong-password-1")
        body = res.get_json()
        body.pop("requestId")
        bodies.append((res.status_code, body))
    assert bodies[0] == bodies[1] == bodies[2]


def test_deactivated_user_cannot_log_in_with_correct_password(app):
    _sql(app, "UPDATE app_user SET is_active = 0 WHERE username = ?", (EXEC,))
    res = _login(app.test_client(), EXEC)
    payload = _assert_error(res, 401, "LOGIN_FAILED")
    assert payload["message"] == LOGIN_FAILED_MESSAGE


def test_deactivating_a_user_ends_their_open_session(app, executive):
    assert executive.get(SESSION).status_code == 200
    _sql(app, "UPDATE app_user SET is_active = 0 WHERE username = ?", (EXEC,))
    _assert_error(executive.get(SESSION), 401, "UNAUTHENTICATED")
    _assert_error(executive.get(ASSETS), 401, "UNAUTHENTICATED")


def test_login_validation_errors_are_400(anon):
    _assert_error(anon.client.post(SESSION, json={"username": ADMIN}), 400, "VALIDATION_FAILED")
    _assert_error(anon.client.post(SESSION, json={}), 400, "VALIDATION_FAILED")
    _assert_error(anon.client.post(SESSION, json={"username": "x", "password": "y", "role": "SYS_ADMIN"}),
                  400, "VALIDATION_FAILED")
    _assert_error(anon.client.post(SESSION, data="username=x&password=y",
                                   content_type="application/x-www-form-urlencoded"), 400, "VALIDATION_FAILED")


def test_login_response_never_echoes_password(anon):
    res = _login(anon.client, ADMIN)
    assert MOCK_PASSWORD not in res.get_data(as_text=True)
    bad = _login(anon.client, ADMIN, "secret-guess-999")
    assert "secret-guess-999" not in bad.get_data(as_text=True)


# --------------------------------------------------------------------------- rate limit

def test_five_failures_then_429_even_with_correct_password(app):
    client = app.test_client()
    for _ in range(5):
        _assert_error(_login(client, ADMIN, "wrong-password-1"), 401, "LOGIN_FAILED")
    payload = _assert_error(_login(client, ADMIN, "wrong-password-1"), 429, "TOO_MANY_ATTEMPTS")
    assert payload["message"]
    _assert_error(_login(client, ADMIN), 429, "TOO_MANY_ATTEMPTS")
    # No session was created by the blocked attempt.
    _assert_error(client.get(SESSION), 401, "UNAUTHENTICATED")


def test_rate_limit_applies_to_unknown_usernames_too(app):
    client = app.test_client()
    for _ in range(5):
        _assert_error(_login(client, "ghost.user", "nope-nope-1"), 401, "LOGIN_FAILED")
    _assert_error(_login(client, "ghost.user", "nope-nope-1"), 429, "TOO_MANY_ATTEMPTS")


def test_rate_limit_is_per_username(app):
    client = app.test_client()
    for _ in range(5):
        _login(client, ADMIN, "wrong-password-1")
    _assert_error(_login(client, ADMIN), 429, "TOO_MANY_ATTEMPTS")
    assert _login(client, EXEC).status_code == 200


def test_successful_login_resets_failure_count(app):
    client = app.test_client()
    for _ in range(4):
        _login(client, ADMIN, "wrong-password-1")
    assert _login(client, ADMIN).status_code == 200
    for _ in range(4):
        _assert_error(_login(client, ADMIN, "wrong-password-1"), 401, "LOGIN_FAILED")
    assert _login(client, ADMIN).status_code == 200


# --------------------------------------------------------------------------- rotation

def test_new_login_rotates_session_and_invalidates_old_cookie(app):
    client = app.test_client()
    first = _login(client, ADMIN)
    old_cookie, old_csrf = _cookie_value(first), first.get_json()["csrfToken"]

    second = _login(client, ADMIN)  # same client, still carrying the old cookie
    assert second.status_code == 200
    new_cookie, new_csrf = _cookie_value(second), second.get_json()["csrfToken"]
    assert new_cookie != old_cookie
    assert new_csrf != old_csrf
    assert client.get_cookie(COOKIE).value == new_cookie

    # The old cookie no longer opens a session.
    _assert_error(_client_with_cookie(app, old_cookie).get(SESSION), 401, "UNAUTHENTICATED")
    # The new one does, and reports the new token.
    assert _client_with_cookie(app, new_cookie).get(SESSION).get_json()["csrfToken"] == new_csrf


def test_csrf_token_from_before_relogin_is_rejected(app):
    api = Api(app, ADMIN)
    old_csrf = api.csrf
    api.login(ADMIN, MOCK_PASSWORD)
    res = api.client.patch(REQUIREMENT, json=_note("Rotated"), headers={"X-CSRF-Token": old_csrf})
    _assert_error(res, 403, "CSRF_INVALID")
    ok = api.patch(REQUIREMENT, json=_note("Rotated"))
    assert ok.status_code == 200, ok.get_json()


@pytest.mark.parametrize("headers", [{}, {"X-CSRF-Token": ""}, {"X-CSRF-Token": "0" * 64},
                                     {"X-CSRF-Token": "été"}])
def test_a_write_without_the_sessions_csrf_token_is_refused(admin, headers):
    res = admin.client.patch(REQUIREMENT, json=_note("No token"), headers=headers)
    _assert_error(res, 403, "CSRF_INVALID")
    assert _ok(admin, REQUIREMENT)["notes"] != "No token"


def test_planted_cookie_is_not_adopted_on_login(app):
    """Session fixation: a cookie value chosen before login must not become the session id."""
    client = _client_with_cookie(app, "attacker-chosen-token-value-0123456789")
    res = _login(client, ADMIN)
    assert res.status_code == 200
    assert _cookie_value(res) != "attacker-chosen-token-value-0123456789"
    _assert_error(_client_with_cookie(app, "attacker-chosen-token-value-0123456789").get(SESSION),
                  401, "UNAUTHENTICATED")


def test_switching_user_on_same_client_ends_previous_session(app):
    client = app.test_client()
    admin_cookie = _cookie_value(_login(client, ADMIN))
    res = _login(client, EXEC)
    assert client.get(SESSION).get_json()["user"]["role"] == "EXECUTIVE"
    assert _cookie_value(res) != admin_cookie
    _assert_error(_client_with_cookie(app, admin_cookie).get(SESSION), 401, "UNAUTHENTICATED")


def test_two_clients_have_independent_sessions(app):
    a = Api(app, ADMIN)
    b = Api(app, ADMIN)
    assert a.csrf != b.csrf
    assert a.get(SESSION).status_code == 200
    assert b.get(SESSION).status_code == 200
    assert a.delete(SESSION).status_code == 204
    assert b.get(SESSION).status_code == 200


# --------------------------------------------------------------------------- logout

def test_logout_invalidates_session(app, admin):
    cookie = admin.client.get_cookie(COOKIE).value
    res = admin.delete(SESSION)
    assert res.status_code == 204
    assert res.get_data() == b""
    cleared = _session_cookie_header(res).lower()
    assert "expires=thu, 01 jan 1970" in cleared or "max-age=0" in cleared

    _assert_error(admin.get(SESSION), 401, "UNAUTHENTICATED")
    _assert_error(admin.get(ASSETS), 401, "UNAUTHENTICATED")
    # Replaying the old cookie value does not resurrect the server-side session.
    replay = _client_with_cookie(app, cookie)
    _assert_error(replay.get(SESSION), 401, "UNAUTHENTICATED")
    _assert_error(replay.patch(REQUIREMENT, json=_note("Ghost"), headers={"X-CSRF-Token": admin.csrf}),
                  401, "UNAUTHENTICATED")


def test_logout_requires_csrf(admin):
    _assert_error(admin.client.delete(SESSION), 403, "CSRF_INVALID")
    assert admin.get(SESSION).status_code == 200


def test_logout_when_signed_out_is_401(anon):
    _assert_error(anon.client.delete(SESSION), 401, "UNAUTHENTICATED")


def test_get_session_when_signed_out_is_401(anon):
    payload = _assert_error(anon.get(SESSION), 401, "UNAUTHENTICATED")
    assert payload["message"]


def test_get_session_with_garbage_cookie_is_401(app):
    _assert_error(_client_with_cookie(app, "not-a-real-session").get(SESSION), 401, "UNAUTHENTICATED")


def test_can_log_in_again_after_logout(admin):
    admin.delete(SESSION)
    admin.login(ADMIN, MOCK_PASSWORD)
    assert _ok(admin, SESSION)["csrfToken"] == admin.csrf


# --------------------------------------------------------------------------- expiry

def test_idle_session_expires_after_30_minutes(admin, clock):
    clock.advance(minutes=31)
    _assert_error(admin.get(SESSION), 401, "UNAUTHENTICATED")
    # Once expired it stays expired, even if the clock is set back.
    clock.advance(minutes=-31)
    _assert_error(admin.get(SESSION), 401, "UNAUTHENTICATED")


def test_idle_expiry_blocks_writes_too(admin, clock):
    clock.advance(minutes=45)
    _assert_error(admin.patch(REQUIREMENT, json=_note("Late")), 401, "UNAUTHENTICATED")


def test_session_survives_under_idle_limit(admin, clock):
    clock.advance(minutes=29)
    assert admin.get(SESSION).status_code == 200


def test_activity_extends_idle_window(admin, clock):
    for _ in range(4):
        clock.advance(minutes=25)
        assert admin.get(ASSETS).status_code == 200
    clock.advance(minutes=31)
    _assert_error(admin.get(SESSION), 401, "UNAUTHENTICATED")


def test_absolute_session_lifetime_is_enforced(admin, clock):
    """Even an active session ends after the absolute limit (12 h by default)."""
    for _ in range(int(12 * 60 / 25)):  # 28 steps of 25 min = 11 h 40 min, always active
        clock.advance(minutes=25)
        assert admin.get(SESSION).status_code == 200
    clock.advance(minutes=25)  # 12 h 05 min after login
    _assert_error(admin.get(SESSION), 401, "UNAUTHENTICATED")


def test_login_works_after_expiry(admin, clock):
    clock.advance(hours=2)
    _assert_error(admin.get(SESSION), 401, "UNAUTHENTICATED")
    admin.login(ADMIN, MOCK_PASSWORD)
    assert admin.get(SESSION).status_code == 200
