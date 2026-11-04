"""Request bodies for user management (system administrators only)."""
from __future__ import annotations

from typing import Annotated, ClassVar

from pydantic import BeforeValidator

from .common import ApiModel, Id, PatchModel, Reason, Version, optional_text, required_text


def _upper(value):
    return value.strip().upper() if isinstance(value, str) else value


Username = required_text(2, 120)
DisplayName = required_text(1, 160)
Role = Annotated[str, BeforeValidator(_upper)]  # checked against APP_ROLE by user_service


class UserCreate(ApiModel):
    """password is optional: left out, the account gets the MOCK password (demo and test profiles only).
    With AUTH_MODE=ldap it must be left out (people sign in with their Windows password) and the username must be a
    directory username such as U12345; user_service checks both."""

    username: Username
    display_name: optional_text(160) = None
    role: Role
    password: str | None = None  # not trimmed or normalised; length is checked by the service
    department_ids: list[Id] = []


class UserUpdate(PatchModel):
    """Partial update. departmentIds replaces the whole list (department-scoped roles only)."""

    REQUIRED_ON_PATCH: ClassVar[tuple[str, ...]] = ("display_name", "role", "active", "department_ids")
    display_name: DisplayName | None = None
    role: Role | None = None
    active: bool | None = None
    department_ids: list[Id] | None = None
    reason: Reason = None
    version: Version | None = None  # optional; when sent, a stale value answers 409 STALE_VERSION
