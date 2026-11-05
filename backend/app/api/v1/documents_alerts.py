"""Documents (versioned files), the alert centre, and Settings administration (lists, roles, alert rules)."""
from __future__ import annotations

from typing import Annotated, ClassVar, Literal

from flask import jsonify, request, send_file
from pydantic import BeforeValidator

from ...exceptions import PayloadTooLarge, ValidationFailed
from ...models import Document
from ...models.documents import DOC_ENTITIES, DOC_TYPES
from ...schemas.capability import ArchiveRequest, _upper
from ...schemas.common import ApiModel, Id, PatchModel, Query, Reason, Version, code_text, required_text
from ...security.auth import PERM_VIEW, admin_only, permission_required
from ...services import admin_service, alert_service, document_service, project_service
from . import body, bp, created, user
from .admin import register_history

register_history("DOCUMENT", Document, "Document")

DocType = Annotated[Literal[DOC_TYPES], BeforeValidator(_upper)]  # type: ignore[valid-type]
DocEntity = Annotated[Literal[DOC_ENTITIES], BeforeValidator(_upper)]  # type: ignore[valid-type]
UPLOAD_LIMIT = document_service.MAX_BYTES + 64 * 1024


class DocumentCreate(ApiModel):
    code: code_text(2, 20)
    title_en: required_text(2, 200)
    title_ar: required_text(2, 200)
    doc_type: DocType
    entity_type: DocEntity
    entity_id: Id


class DocumentUpdate(PatchModel):
    REQUIRED_ON_PATCH: ClassVar[tuple[str, ...]] = ("title_en", "title_ar", "doc_type")
    title_en: required_text(2, 200) | None = None
    title_ar: required_text(2, 200) | None = None
    doc_type: DocType | None = None
    reason: Reason = None
    version: Version | None = None


@bp.get("/documents")
@permission_required(PERM_VIEW)
def list_documents():
    q = Query(request.args, {"q", "type", "entityType", "entityId"})
    return jsonify(document_service.list_documents(user(), {
        "q": q.text("q", 100), "type": q.choice("type", DOC_TYPES), "entityType": q.choice("entityType", DOC_ENTITIES),
        "entityId": q.id("entityId")}))


@bp.get("/documents/next-code")
@permission_required(PERM_VIEW)
def next_document_code():
    Query(request.args, set())
    return jsonify({"code": project_service.next_code(Document, "DOC")})


@bp.get("/documents/<int:document_id>")
@permission_required(PERM_VIEW)
def get_document(document_id: int):
    Query(request.args, set())
    return jsonify(document_service.get_document(user(), document_id))


@bp.post("/documents")
def create_document():
    result = document_service.create_document(user(), DocumentCreate.model_validate(body()))
    return created(result, f"/api/v1/documents/{result['id']}")


@bp.patch("/documents/<int:document_id>")
def update_document(document_id: int):
    return jsonify(document_service.update_document(user(), document_id, DocumentUpdate.model_validate(body())))


@bp.post("/documents/<int:document_id>/archive")
def archive_document(document_id: int):
    data = ArchiveRequest.model_validate(body())
    return jsonify(document_service.archive_document(user(), document_id, data.archived, data.version, data.reason))


@bp.post("/documents/<int:document_id>/versions")
def upload_version(document_id: int):
    """multipart/form-data: file, note. The only route allowed past the 64 KiB request limit (20 MB)."""
    request.max_content_length = UPLOAD_LIMIT
    if request.content_length is not None and request.content_length > UPLOAD_LIMIT:
        raise PayloadTooLarge("Files are limited to 20 MB.")
    upload = request.files.get("file")
    if upload is None:
        raise ValidationFailed.field("file", "Choose a file.")
    data = upload.read(document_service.MAX_BYTES + 1)
    note = (request.form.get("note") or "").strip() or None
    result = document_service.add_version(user(), document_id, upload.filename or "file", data, note)
    return created(result, f"/api/v1/documents/{document_id}")


@bp.get("/documents/<int:document_id>/file")
@permission_required(PERM_VIEW)
def download_document(document_id: int):
    q = Query(request.args, {"version"})
    raw = q.text("version", 6)
    if raw is not None and not raw.isdigit():
        raise ValidationFailed.field("version", "Must be a version number.")
    version, path = document_service.download(user(), document_id, int(raw) if raw else None)
    inline = version.content_type in ("application/pdf", "image/png", "image/jpeg")
    response = send_file(path, mimetype=version.content_type, as_attachment=not inline, download_name=version.file_name,
                         max_age=0)
    return response


# ---------------------------------------------------------------- alerts -------------------------------------------


class AckRequest(ApiModel):
    keys: list[str]


@bp.get("/alerts")
@permission_required(PERM_VIEW)
def list_alerts():
    q = Query(request.args, {"open"})
    return jsonify(alert_service.alerts_for(user(), include_acked=not q.boolean("open")))


@bp.get("/alerts/count")
@permission_required(PERM_VIEW)
def alert_count():
    Query(request.args, set())
    data = alert_service.alerts_for(user(), include_acked=False)
    return jsonify({"open": data["open"], "counts": data["counts"]})


@bp.post("/alerts/acknowledge")
@permission_required(PERM_VIEW)
def acknowledge_alerts():
    data = AckRequest.model_validate(body())
    if not 1 <= len(data.keys) <= 500:
        raise ValidationFailed.field("keys", "Send 1 to 500 alert keys.")
    return jsonify(alert_service.acknowledge(user(), data.keys))


class RuleUpdate(ApiModel):
    roles: list[str]
    enabled: bool
    days_ahead: int | None = None
    version: int | None = None


@bp.get("/alert-rules")
@admin_only
def list_alert_rules():
    Query(request.args, set())
    return jsonify({"items": alert_service.list_rules(user())})


@bp.put("/alert-rules/<alert_type>")
@admin_only
def put_alert_rule(alert_type: str):
    data = RuleUpdate.model_validate(body())
    if data.days_ahead is not None and not 0 <= data.days_ahead <= 3650:
        raise ValidationFailed.field("daysAhead", "Must be 0 to 3650 days.")
    return jsonify(alert_service.update_rule(user(), alert_type.upper(), data.roles, data.enabled, data.days_ahead,
                                             data.version or None))


# ---------------------------------------------------------------- settings lists and roles ---------------------------


@bp.get("/admin/lists/<kind>")
@admin_only
def admin_list(kind: str):
    Query(request.args, set())
    return jsonify({"items": admin_service.list_entries(user(), kind)})


@bp.post("/admin/lists/<kind>")
@admin_only
def admin_create(kind: str):
    result = admin_service.create_entry(user(), kind, body())
    return created(result, f"/api/v1/admin/lists/{kind}/{result['id']}")


@bp.patch("/admin/lists/<kind>/<int:entry_id>")
@admin_only
def admin_update(kind: str, entry_id: int):
    return jsonify(admin_service.update_entry(user(), kind, entry_id, body()))


@bp.post("/admin/lists/<kind>/<int:entry_id>/archive")
@admin_only
def admin_archive(kind: str, entry_id: int):
    data = ArchiveRequest.model_validate(body())
    return jsonify(admin_service.archive_entry(user(), kind, entry_id, data.archived, data.version, data.reason))


class StageOrder(ApiModel):
    stage_ids: list[Id]


@bp.put("/admin/project-types/<int:type_id>/stage-order")
@admin_only
def reorder_stages(type_id: int):
    data = StageOrder.model_validate(body())
    return jsonify({"items": admin_service.reorder_stages(user(), type_id, data.stage_ids)})


@bp.get("/admin/roles")
@admin_only
def list_roles():
    Query(request.args, set())
    return jsonify(admin_service.list_roles(user()))


@bp.post("/admin/roles")
@admin_only
def create_role():
    result = admin_service.save_role(user(), body())
    return created(result, f"/api/v1/admin/roles/{result['id']}")


@bp.patch("/admin/roles/<int:role_id>")
@admin_only
def update_role(role_id: int):
    return jsonify(admin_service.save_role(user(), body(), role_id))
