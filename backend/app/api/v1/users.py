"""User management (system administrators only): list, create, read and update users, their role and departments.

There is no sign-up and no password-reset endpoint yet: a user created without a password gets the MOCK password
(demo and test profiles only; see security/mock_credentials.py). With AUTH_MODE=ldap people sign in with their
Windows password: no password is sent or stored, and GET /users/directory-lookup fills in the display name.
"""
from __future__ import annotations

from flask import Response, jsonify, request

from ...exceptions import PayloadTooLarge, ValidationFailed
from ...schemas.common import Query
from ...schemas.user import UserCreate, UserUpdate
from ...security.auth import admin_only
from ...services import user_import, user_service
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


@bp.get("/users/import-template")
@admin_only
def users_import_template():
    """The Excel file to fill in with the people to add (?lang=en|ar)."""
    query = Query(request.args, {"lang"})
    content, name = user_import.template((query.choice("lang", ("EN", "AR")) or "EN").lower())
    response = Response(content, mimetype=user_import.MEDIA_TYPE)
    response.headers["Content-Disposition"] = f'attachment; filename="{name}"'
    return response


def _uploaded_workbook() -> tuple[bytes, str]:
    """multipart/form-data: file. The only user routes allowed past the 64 KiB request limit (2 MB)."""
    request.max_content_length = user_import.MAX_FILE_BYTES + 64 * 1024
    if request.content_length is not None and request.content_length > request.max_content_length:
        raise PayloadTooLarge(f"The file is larger than {user_import.MAX_FILE_BYTES // (1024 * 1024)} MB.")
    upload = request.files.get("file")
    if upload is None:
        raise ValidationFailed.field("file", "Choose the Excel file.")
    return upload.read(user_import.MAX_FILE_BYTES + 1), upload.filename or ""


@bp.post("/users/import/check")
@admin_only
def users_import_check():
    """What importing this file would do, row by row. Nothing is written."""
    data, name = _uploaded_workbook()
    return jsonify(user_import.check(user(), data, name))


@bp.post("/users/import")
@admin_only
def users_import():
    """Add every person of the file in one transaction (409 IMPORT_HAS_PROBLEMS while a row has a problem)."""
    data, name = _uploaded_workbook()
    return jsonify(user_import.import_file(user(), data, name))


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
