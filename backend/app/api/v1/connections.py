"""Settings > connections: the company directory (LDAP), the main database, trusted certificates and approved
destinations (ported from the Asset Availability project's Settings tab).

Every route is admin_only (system administrators; a role preview is refused too). Sensitive steps (apply, switch on or
off, delete, a secret, the sign-in method, a certificate, a destination, the ldap.env import) also need the password
typed again within the last minutes (POST /connections/reauth; else 403 REAUTH_REQUIRED). Secrets are never returned.
Writes are CSRF-checked like every other POST/PUT/PATCH/DELETE.
"""
from __future__ import annotations

from flask import jsonify, request

from ...exceptions import PayloadTooLarge, ValidationFailed
from ...schemas.common import Query
from ...schemas.connections import (Apply, DraftSave, EgressCreate, EgressUpdate, ProfileCreate, Reauth, Rollback,
                                    SignInMethod, TestRequest, VersionOnly)
from ...security.auth import admin_only, reauthenticate
from ...services.connections import certs, connection_service
from . import body, bp, created, user


@bp.post("/connections/reauth")
@admin_only
def connections_reauth():
    reauthenticate(user(), Reauth.model_validate(body()).password)
    return jsonify({"ok": True})


@bp.get("/connections/overview")
@admin_only
def connections_overview():
    Query(request.args, set())
    return jsonify(connection_service.overview())


@bp.get("/connections/providers")
@admin_only
def connections_providers():
    Query(request.args, set())
    return jsonify(connection_service.providers())


@bp.get("/connections/profiles")
@admin_only
def connections_profiles():
    query = Query(request.args, {"kind"})
    return jsonify(connection_service.list_profiles(query.choice("kind", ("LDAP", "DATABASE"))))


@bp.post("/connections/profiles")
@admin_only
def connections_create_profile():
    result = connection_service.create_profile(user(), ProfileCreate.model_validate(body()))
    return created(result, f"/api/v1/connections/profiles/{result['id']}")


@bp.get("/connections/profiles/<int:profile_id>")
@admin_only
def connections_profile(profile_id: int):
    Query(request.args, set())
    return jsonify(connection_service.get_profile(profile_id))


@bp.put("/connections/profiles/<int:profile_id>/draft")
@admin_only
def connections_save_draft(profile_id: int):
    return jsonify(connection_service.save_draft(user(), profile_id, DraftSave.model_validate(body())))


@bp.post("/connections/profiles/<int:profile_id>/draft/discard")
@admin_only
def connections_discard_draft(profile_id: int):
    return jsonify(connection_service.discard_draft(user(), profile_id, VersionOnly.model_validate(body())))


@bp.post("/connections/profiles/<int:profile_id>/test")
@admin_only
def connections_test(profile_id: int):
    return jsonify(connection_service.run_test(user(), profile_id, TestRequest.model_validate(body())))


@bp.post("/connections/profiles/<int:profile_id>/apply")
@admin_only
def connections_apply(profile_id: int):
    return jsonify(connection_service.apply(user(), profile_id, Apply.model_validate(body())))


@bp.post("/connections/profiles/<int:profile_id>/enable")
@admin_only
def connections_enable(profile_id: int):
    return jsonify(connection_service.set_enabled(user(), profile_id, VersionOnly.model_validate(body()), True))


@bp.post("/connections/profiles/<int:profile_id>/disable")
@admin_only
def connections_disable(profile_id: int):
    return jsonify(connection_service.set_enabled(user(), profile_id, VersionOnly.model_validate(body()), False))


@bp.post("/connections/profiles/<int:profile_id>/rollback")
@admin_only
def connections_rollback(profile_id: int):
    return jsonify(connection_service.rollback(user(), profile_id, Rollback.model_validate(body())))


@bp.delete("/connections/profiles/<int:profile_id>")
@admin_only
def connections_delete(profile_id: int):
    connection_service.delete_profile(user(), profile_id, VersionOnly.model_validate(body()))
    return "", 204


@bp.get("/connections/sign-in")
@admin_only
def connections_sign_in():
    Query(request.args, set())
    return jsonify(connection_service.sign_in_status())


@bp.put("/connections/sign-in")
@admin_only
def connections_set_sign_in():
    return jsonify(connection_service.set_sign_in_method(user(), SignInMethod.model_validate(body())))


@bp.get("/connections/certificates")
@admin_only
def connections_certs():
    Query(request.args, set())
    return jsonify(connection_service.list_certs())


@bp.post("/connections/certificates")
@admin_only
def connections_upload_cert():
    """multipart/form-data: name, file (one certificate, PEM or DER, at most 64 KB)."""
    request.max_content_length = certs.MAX_BYTES + 16 * 1024
    if request.content_length is not None and request.content_length > request.max_content_length:
        raise PayloadTooLarge("A certificate file is at most 64 KB.")
    upload = request.files.get("file")
    if upload is None:
        raise ValidationFailed.field("file", "Choose one certificate file (.cer, .crt or .pem).")
    data = upload.read(certs.MAX_BYTES + 1)
    result = connection_service.upload_cert(user(), request.form.get("name", ""), data)
    return created(result, f"/api/v1/connections/certificates/{result['id']}")


@bp.delete("/connections/certificates/<int:cert_id>")
@admin_only
def connections_archive_cert(cert_id: int):
    connection_service.archive_cert(user(), cert_id, VersionOnly.model_validate(body()))
    return "", 204


@bp.get("/connections/destinations")
@admin_only
def connections_rules():
    Query(request.args, set())
    return jsonify(connection_service.list_rules())


@bp.post("/connections/destinations")
@admin_only
def connections_create_rule():
    result = connection_service.create_rule(user(), EgressCreate.model_validate(body()))
    return created(result, f"/api/v1/connections/destinations/{result['id']}")


@bp.patch("/connections/destinations/<int:rule_id>")
@admin_only
def connections_update_rule(rule_id: int):
    return jsonify(connection_service.update_rule(user(), rule_id, EgressUpdate.model_validate(body())))


@bp.delete("/connections/destinations/<int:rule_id>")
@admin_only
def connections_archive_rule(rule_id: int):
    connection_service.archive_rule(user(), rule_id, VersionOnly.model_validate(body()))
    return "", 204


@bp.get("/connections/database")
@admin_only
def connections_database():
    Query(request.args, set())
    return jsonify(connection_service.database_status())


@bp.get("/connections/history")
@admin_only
def connections_history():
    query = Query(request.args, {"page", "size"})
    page, size = query.page()
    return jsonify(connection_service.history(page, size))


@bp.get("/connections/diagnostics")
@admin_only
def connections_diagnostics():
    Query(request.args, set())
    return jsonify(connection_service.diagnostics())


@bp.post("/connections/import-env")
@admin_only
def connections_import_env():
    return jsonify(connection_service.import_env(user()))
