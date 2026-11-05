"""Versioned documents attached to capabilities, assets, projects, tests, maintenance, suppliers and contracts.

A document is visible to whoever may see the record it is attached to (that record's department scope). Every upload
is a new, immutable version; the file's type is decided from its bytes, never from the name or the browser's claim.
Files are stored once per content under data/files/<sha256>."""
from __future__ import annotations

import hashlib
import re
import zipfile
from io import BytesIO
from pathlib import Path

from sqlalchemy import func, or_, select

from ..core.config import DATA_DIR
from ..core.clock import iso_utc
from ..exceptions import NotFound, PayloadTooLarge, ValidationFailed
from ..models import (AppUser, Asset, CapabilityModel, CapabilityRequirement, Contract, Department, Document,
                      DocumentVersion, MaintenanceOrder, Organization, Project, TestEvent)
from ..repositories import common as repo
from ..schemas.dto import record_meta, sid
from ..security.auth import ALL_DEPARTMENTS, PERM_EDIT_DOCUMENTS, department_scope, require_department_access
from . import audit_service, context, crud, lookup_service as lk

MAX_BYTES = 20 * 1024 * 1024


def files_dir() -> Path:
    """data/files (demo and Oracle); the test profile keeps its files apart."""
    return DATA_DIR / ("files-test" if context.settings().profile == "test" else "files")

_ENTITIES = {
    "CAPABILITY_MODEL": (CapabilityModel, lambda e: None, lambda e: (e.code, e.name_en, e.name_ar)),
    "ASSET": (Asset, lambda e: e.department_id, lambda e: (e.code, e.code, e.code)),
    "PROJECT": (Project, lambda e: e.department_id, lambda e: (e.code, e.name_en, e.name_ar)),
    "TEST_EVENT": (TestEvent, lambda e: e.department_id, lambda e: (e.code, e.title_en, e.title_ar)),
    "MAINTENANCE_ORDER": (MaintenanceOrder, lambda e: context.session().get(Asset, e.asset_id).department_id,
                          lambda e: (e.code, e.title_en, e.title_ar)),
    "ORGANIZATION": (Organization, lambda e: None, lambda e: (e.code, e.name_en, e.name_ar)),
    "CONTRACT": (Contract, lambda e: None, lambda e: (e.code, e.title_en, e.title_ar)),
    "CAPABILITY_REQUIREMENT": (CapabilityRequirement, lambda e: e.department_id, lambda e: (e.code, e.name_en, e.name_ar)),
}
_LINKS = {"CAPABILITY_MODEL": "/models/{id}", "ASSET": "/assets/{id}", "PROJECT": "/projects/{id}",
          "TEST_EVENT": "/testing", "MAINTENANCE_ORDER": "/maintenance", "ORGANIZATION": "/settings",
          "CONTRACT": "/settings", "CAPABILITY_REQUIREMENT": "/requirements/{id}"}


def sniff(data: bytes, file_name: str) -> str:
    """The content type from the bytes. Allowed: PDF, PNG, JPEG, Office (docx/xlsx/pptx) and UTF-8 text/CSV."""
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"PK\x03\x04"):
        try:
            names = set(zipfile.ZipFile(BytesIO(data)).namelist())
        except zipfile.BadZipFile:
            names = set()
        if "word/document.xml" in names:
            return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        if "xl/workbook.xml" in names:
            return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        if "ppt/presentation.xml" in names:
            return "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    if file_name.lower().endswith((".txt", ".csv")):
        try:
            text = data.decode("utf-8")
            if "\x00" not in text:
                return "text/csv" if file_name.lower().endswith(".csv") else "text/plain"
        except UnicodeDecodeError:
            pass
    raise ValidationFailed.field("file", "Only PDF, PNG, JPEG, Word, Excel, PowerPoint, text or CSV files can be added.")


def _target(entity_type: str, entity_id: int):
    spec = _ENTITIES.get(entity_type)
    if spec is None:
        raise ValidationFailed.field("entityType", "Documents cannot be attached to that kind of record.")
    model, dept_of, label = spec
    entity = context.session().get(model, entity_id)
    if entity is None:
        raise ValidationFailed.field("entityId", "The record was not found.")
    return entity, dept_of(entity), label(entity)


def _versions(doc: Document) -> list[DocumentVersion]:
    return list(context.session().scalars(select(DocumentVersion).where(DocumentVersion.document_id == doc.id)
                                          .order_by(DocumentVersion.version_no.desc())))


def document_dto(doc: Document, with_versions: bool = False) -> dict:
    session = context.session()
    model = _ENTITIES[doc.entity_type][0]
    entity = session.get(model, doc.entity_id)
    code, en, ar = _ENTITIES[doc.entity_type][2](entity) if entity else ("?", "?", "?")
    latest = session.scalar(select(DocumentVersion).where(DocumentVersion.document_id == doc.id,
                                                          DocumentVersion.version_no == doc.current_version))
    uploader = session.get(AppUser, latest.uploaded_by) if latest else None
    out = {"id": sid(doc.id), "code": doc.code, "titleEn": doc.title_en, "titleAr": doc.title_ar, "docType": doc.doc_type,
           "linked": {"type": doc.entity_type, "id": sid(doc.entity_id), "code": code, "nameEn": en, "nameAr": ar,
                      "link": _LINKS[doc.entity_type].format(id=doc.entity_id)},
           "department": lk.ref_id(Department, doc.department_id), "currentVersion": doc.current_version,
           "latest": {"fileName": latest.file_name, "contentType": latest.content_type, "sizeBytes": latest.size_bytes,
                      "uploadedAt": iso_utc(latest.uploaded_at), "uploadedBy": uploader.display_name if uploader else None}
           if latest else None,
           **record_meta(doc)}
    if with_versions:
        out["versions"] = [{"id": sid(v.id), "versionNo": v.version_no, "fileName": v.file_name,
                            "contentType": v.content_type, "sizeBytes": v.size_bytes, "note": v.note,
                            "uploadedAt": iso_utc(v.uploaded_at),
                            "uploadedBy": (session.get(AppUser, v.uploaded_by) or AppUser(display_name="?")).display_name}
                           for v in _versions(doc)]
    return out


def list_documents(actor, f: dict) -> dict:
    query = select(Document).where(Document.archived_at.is_(None))
    scope = department_scope(actor)
    if scope is not ALL_DEPARTMENTS:
        query = query.where(or_(Document.department_id.is_(None), Document.department_id.in_(sorted(scope) or [-1])))
    if f.get("q"):
        pattern = repo.like_pattern(f["q"])
        query = query.where(or_(func.lower(Document.code).like(pattern, escape="\\"),
                                func.lower(Document.title_en).like(pattern, escape="\\"),
                                func.lower(Document.title_ar).like(pattern, escape="\\")))
    if f.get("type"):
        query = query.where(Document.doc_type == f["type"])
    if f.get("entityType"):
        query = query.where(Document.entity_type == f["entityType"])
    if f.get("entityId"):
        query = query.where(Document.entity_id == f["entityId"])
    rows = list(context.session().scalars(query.order_by(Document.updated_at.desc(), Document.id.desc()).limit(500)))
    return {"items": [document_dto(d) for d in rows]}


def _load(actor, document_id: int, for_update: bool = False) -> Document:
    doc = repo.get(context.session(), Document, document_id, for_update=for_update)
    if doc is None:
        raise NotFound(f"Document {document_id} was not found.")
    if doc.department_id is not None:
        require_department_access(actor, doc.department_id, f"Document {document_id} was not found.")
    return doc


def get_document(actor, document_id: int) -> dict:
    return document_dto(_load(actor, document_id), with_versions=True)


def _store(data: bytes) -> str:
    digest = hashlib.sha256(data).hexdigest()
    path = files_dir() / digest[:2] / digest
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".part")
        tmp.write_bytes(data)
        tmp.replace(path)
    return digest


def _clean_name(name: str) -> str:
    name = Path(name or "file").name
    name = re.sub(r"[\x00-\x1f\\/:*?\"<>|]", "_", name).strip() or "file"
    return name[:200]


def create_document(actor, data) -> dict:
    entity, department_id, _ = _target(data.entity_type, data.entity_id)
    if department_id is not None:
        require_department_access(actor, department_id, "The record was not found.")
    crud.check_unique_code(Document, data.code)
    doc = Document(code=data.code, title_en=data.title_en, title_ar=data.title_ar, doc_type=data.doc_type,
                   entity_type=data.entity_type, entity_id=entity.id, department_id=department_id, current_version=0)
    crud.create(actor, doc, PERM_EDIT_DOCUMENTS, department_id)
    return get_document(actor, doc.id)


def add_version(actor, document_id: int, file_name: str, data: bytes, note: str | None) -> dict:
    doc = _load(actor, document_id, for_update=True)
    from ..security.auth import require_edit
    require_edit(actor, PERM_EDIT_DOCUMENTS, doc.department_id)
    if not data:
        raise ValidationFailed.field("file", "The file is empty.")
    if len(data) > MAX_BYTES:
        raise PayloadTooLarge(f"Files are limited to {MAX_BYTES // (1024 * 1024)} MB.")
    if note is not None and len(note) > 500:
        raise ValidationFailed.field("note", "Must be at most 500 characters.")
    name = _clean_name(file_name)
    content_type = sniff(data, name)
    digest = _store(data)
    session = context.session()
    before = audit_service.snapshot(doc)
    version = DocumentVersion(document_id=doc.id, version_no=doc.current_version + 1, file_name=name,
                              content_type=content_type, size_bytes=len(data), sha256=digest, note=note or None,
                              uploaded_at=context.now(), uploaded_by=actor.id)
    session.add(version)
    doc.current_version = version.version_no
    context.stamp_update(doc, actor, context.now())
    session.flush()
    audit_service.record(actor, "UPLOAD", doc, before, audit_service.snapshot(doc), note,
                         extra={"links": {"fileName": name, "versionNo": version.version_no}})
    session.commit()
    return get_document(actor, doc.id)


def download(actor, document_id: int, version_no: int | None) -> tuple[DocumentVersion, Path]:
    doc = _load(actor, document_id)
    number = version_no or doc.current_version
    version = context.session().scalar(select(DocumentVersion).where(DocumentVersion.document_id == doc.id,
                                                                     DocumentVersion.version_no == number))
    if version is None:
        raise NotFound("That version was not found.")
    path = files_dir() / version.sha256[:2] / version.sha256
    if not path.is_file():
        raise NotFound("The stored file is missing. Ask an administrator to restore it from backup.")
    return version, path


def update_document(actor, document_id: int, data) -> dict:
    doc = _load(actor, document_id, for_update=True)
    changes = {k: v for k, v in data.changes().items() if k in ("title_en", "title_ar", "doc_type")}
    crud.update(actor, doc, changes, PERM_EDIT_DOCUMENTS, data.version, data.reason, department_ids=(doc.department_id,))
    return get_document(actor, doc.id)


def archive_document(actor, document_id: int, archived: bool, version, reason) -> dict:
    doc = _load(actor, document_id, for_update=True)
    crud.set_archived(actor, doc, archived, PERM_EDIT_DOCUMENTS, version, reason)
    return get_document(actor, doc.id)
