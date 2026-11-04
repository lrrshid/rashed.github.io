"""Domain errors. Each maps to one HTTP status and the uniform error body {code, message, fieldErrors, requestId}."""
from __future__ import annotations


class AppError(Exception):
    status = 400
    code = "BAD_REQUEST"

    def __init__(self, message: str, field_errors: list[dict] | None = None, code: str | None = None):
        super().__init__(message)
        self.message = message
        self.field_errors = field_errors or []
        if code:
            self.code = code


class ValidationFailed(AppError):
    status = 400
    code = "VALIDATION_FAILED"

    @classmethod
    def field(cls, field: str, message: str) -> "ValidationFailed":
        return cls("Please correct the highlighted fields.", [{"field": field, "message": message}])


class Unauthenticated(AppError):
    status = 401
    code = "UNAUTHENTICATED"


class Forbidden(AppError):
    status = 403
    code = "FORBIDDEN"


class NotFound(AppError):
    status = 404
    code = "NOT_FOUND"


class Conflict(AppError):
    status = 409
    code = "CONFLICT"


class Duplicate(Conflict):
    code = "DUPLICATE"

    @classmethod
    def field(cls, field: str, message: str) -> "Duplicate":
        return cls(message, [{"field": field, "message": message}])


class DependencyConflict(Conflict):
    code = "DEPENDENCY"


class StaleVersion(Conflict):
    code = "STALE_VERSION"

    def __init__(self, message: str = "This record was changed by someone else. Reload to see the latest version."):
        super().__init__(message)


class InvalidTransition(Conflict):
    code = "INVALID_TRANSITION"


class PayloadTooLarge(AppError):
    status = 413
    code = "PAYLOAD_TOO_LARGE"


class TooManyAttempts(AppError):
    status = 429
    code = "TOO_MANY_ATTEMPTS"


class Busy(AppError):
    status = 503
    code = "BUSY"


class DirectoryUnavailable(AppError):
    """The company directory (LDAP) did not answer, or its certificate or service account is wrong (AUTH_MODE=ldap).
    The technical cause is logged on the server, never sent to the browser."""

    status = 503
    code = "DIRECTORY_UNAVAILABLE"

    MESSAGE = "The company directory cannot be reached. Try again in a few minutes or contact IT."

    def __init__(self, detail: str | None = None, hint: str | None = None):
        super().__init__(self.MESSAGE)
        self.detail = detail  # technical cause, for the server log and the check-ldap command only
        self.hint = hint      # what IT should check, in plain words
