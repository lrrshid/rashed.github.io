"""CSRF protection: every state-changing /api request must echo the session's token in X-CSRF-Token.

The token is created with the server-side session at login and returned by GET/POST /session.
POST /session itself is exempt: a signed-out browser has no token yet, and login is covered by
SameSite=Strict cookies, same-origin-only access and the login throttle.
"""
from __future__ import annotations

import hmac
import secrets

from flask import g, request

from ..exceptions import Forbidden

HEADER = "X-CSRF-Token"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def new_token() -> str:
    return secrets.token_hex(32)


def enforce() -> None:
    if request.method in SAFE_METHODS:
        return
    expected = getattr(g, "csrf_token", None)
    supplied = request.headers.get(HEADER, "")
    # Compare bytes: compare_digest raises TypeError for a str with non-ASCII characters, which would be a 500.
    if not expected or not supplied or not hmac.compare_digest(expected.encode(), supplied.encode("utf-8", "replace")):
        raise Forbidden("Missing or invalid security token. Reload the page and try again.", code="CSRF_INVALID")
