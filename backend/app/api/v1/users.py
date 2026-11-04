"""User management (system administrators only): list, create, read and update users, their role and departments.

There is no sign-up and no password-reset endpoint yet: a user created without a password gets the MOCK password
(demo and test profiles only; see security/mock_credentials.py). With AUTH_MODE=ldap people sign in with their
Windows password: no password is sent or stored, and GET /users/directory-lookup fills in the display name.
"""
from __future__ import annotations

from flask import jsonify, request

from ...schemas.common import Query
from ...schemas.user import UserCreate, UserUpdate
from ...security.auth import admin_only
from ...services import user_service
from . import body, bp, created, user


@bp.get("/users")
@admin_only
def list_users():
    query = Query(request.args, {"q"})
    page, size = query.page()
    return jsonify(user_service.list_users(user(), query.text("q"), page, size))


@bp.post("/users")
@admin_only
def create_user():
    data = UserCreate.model_validate(body())
    result = user_service.create_user_as_admin(user(), data)
    return created(result, f"/api/v1/users/{result['id']}")


@bp.get("/users/directory-lookup")
@admin_only
def directory_lookup():
    """AUTH_MODE=ldap: a person's display name from the company directory (?username=U12345)."""
    query = Query(request.args, {"username"})
    return jsonify(user_service.directory_lookup(user(), query.text("username", 120)))


@bp.get("/users/<int:user_id>")
@admin_only
def get_user(user_id: int):
    Query(request.args, set())
    return jsonify(user_service.get_user(user(), user_id))


@bp.patch("/users/<int:user_id>")
@admin_only
def update_user(user_id: int):
    data = UserUpdate.model_validate(body())
    return jsonify(user_service.update_user(user(), user_id, data))
