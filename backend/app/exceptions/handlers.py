"""Turns every failure into the single error format. Stack traces and SQL never reach the client."""
from __future__ import annotations

import logging

from flask import Flask, current_app, g, jsonify, request, send_from_directory
from pydantic import ValidationError
from sqlalchemy.exc import DBAPIError, IntegrityError, OperationalError
from sqlalchemy.orm.exc import StaleDataError
from werkzeug.exceptions import HTTPException, MethodNotAllowed, NotFound

from ..core.config import FRONTEND_DIR
from .errors import AppError

log = logging.getLogger("cpc.errors")

_HTTP_CODES = {
    400: ("BAD_REQUEST", "The request could not be understood."),
    401: ("UNAUTHENTICATED", "Please sign in."),
    403: ("FORBIDDEN", "You do not have permission to do that."),
    404: ("NOT_FOUND", "The requested resource was not found."),
    405: ("METHOD_NOT_ALLOWED", "That action is not supported here."),
    413: ("PAYLOAD_TOO_LARGE", "The request is too large."),
    415: ("UNSUPPORTED_MEDIA_TYPE", "Send JSON with Content-Type: application/json."),
}


def error_body(code: str, message: str, field_errors: list | None = None) -> dict:
    return {
        "code": code,
        "message": message,
        "fieldErrors": field_errors or [],
        "requestId": getattr(g, "request_id", None),
    }


def _json(status: int, code: str, message: str, field_errors: list | None = None):
    return jsonify(error_body(code, message, field_errors)), status


def pydantic_field_errors(exc: ValidationError) -> list[dict]:
    out = []
    for err in exc.errors(include_url=False, include_input=False):
        loc = [str(p) for p in err.get("loc", ()) if p != "body"]
        field = ".".join(loc) if loc else "_"
        message = err.get("msg", "Invalid value")
        if message.startswith("Value error, "):
            message = message[len("Value error, "):]
        if err.get("type") == "extra_forbidden":
            message = "Unknown field."
        if err.get("type") == "missing":
            message = "This field is required."
        out.append({"field": field, "message": message})
    return out


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(AppError)
    def _app_error(exc: AppError):
        return _json(exc.status, exc.code, exc.message, exc.field_errors)

    @app.errorhandler(ValidationError)
    def _validation(exc: ValidationError):
        return _json(400, "VALIDATION_FAILED", "Please correct the highlighted fields.", pydantic_field_errors(exc))

    @app.errorhandler(StaleDataError)
    def _stale(_exc):
        return _json(409, "STALE_VERSION", "This record was changed by someone else. Reload to see the latest version.")

    @app.errorhandler(IntegrityError)
    def _integrity(exc: IntegrityError):
        # Services pre-check uniqueness and parents; this is the database backstop (e.g. a race).
        log.warning("integrity violation", extra={"fields": {"error": type(exc.orig).__name__}})
        return _json(409, "CONFLICT", "The change conflicts with existing data. Reload and try again.")

    @app.errorhandler(OperationalError)
    def _operational(exc: OperationalError):
        if "locked" in str(exc.orig).lower() or "busy" in str(exc.orig).lower():
            return _json(503, "BUSY", "The database is busy. Please try again.")
        # Log the driver error type only: SQL text and values may contain defect content.
        log.error("database error", extra={"fields": {"error": type(exc.orig).__name__}})
        return _json(503, "DATABASE_UNAVAILABLE", "The database is unavailable. Please try again later.")

    def _api_rule_matches(exc: MethodNotAllowed) -> bool:
        """True if an API rule (not the frontend catch-all) matches this path for one of its allowed methods."""
        adapter = current_app.url_map.bind_to_environ(request.environ)
        for method in exc.valid_methods or ():
            if method in ("HEAD", "OPTIONS"):
                continue
            try:
                rule, _ = adapter.match(method=method, return_rule=True)
            except HTTPException:
                continue
            if rule.endpoint != "frontend":
                return True
        return False

    @app.errorhandler(HTTPException)
    def _http(exc: HTTPException):
        if request.path == "/api" or request.path.startswith("/api/"):
            if isinstance(exc, MethodNotAllowed) and not _api_rule_matches(exc):
                # e.g. PATCH /api/v1/defects/0: no API rule matches (ids are 1..2^63-1), only the GET-only
                # frontend catch-all does. That is an unknown path, so 404. A real API route (also a POST-only
                # one such as /ships/{id}/archive) keeps its 405.
                exc = NotFound()
            code, message = _HTTP_CODES.get(exc.code, ("HTTP_ERROR", exc.name))
            return _json(exc.code or 500, code, message)
        if exc.code == 404:
            return send_from_directory(FRONTEND_DIR, "404.html"), 404
        return exc

    @app.errorhandler(Exception)
    def _unexpected(exc: Exception):
        if isinstance(exc, DBAPIError):
            log.error("unhandled database error", extra={"fields": {"error": type(exc.orig).__name__}})
        else:
            log.error("unhandled error", exc_info=exc)
        return _json(500, "INTERNAL_ERROR", "Something went wrong. Quote the request id if you report this.")
