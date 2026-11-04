"""Capability models (platforms / systems) and capability requirements: lists, profiles, create, update, archive."""
from __future__ import annotations

import json

from sqlalchemy import func, or_, select

from ..exceptions import ValidationFailed
from ..models import (Asset, CapabilityCategory, CapabilityModel, CapabilityRequirement, Department, Organization,
                      ProjectModel, RequirementModel, SpecField)
from ..repositories import common as repo
from ..schemas.dto import record_meta, sid
from ..security.auth import ALL_DEPARTMENTS, PERM_EDIT_MODELS, PERM_EDIT_REQUIREMENTS, department_scope
from . import audit_service, context, crud, lookup_service as lk, metrics_service

# ---------------------------------------------------------------- models -------------------------------------------


def _specs(model: CapabilityModel) -> dict:
    return json.loads(model.specs_json) if model.specs_json else {}


def model_dto(m: CapabilityModel, counts: dict[str, int] | None = None, full: bool = False) -> dict:
    out = {
        "id": sid(m.id), "code": m.code, "nameEn": m.name_en, "nameAr": m.name_ar,
        "category": lk.ref_id(CapabilityCategory, m.category_id),
        "manufacturer": lk.ref_id(Organization, m.manufacturer_id),
        "roleEn": m.role_en, "roleAr": m.role_ar, "unitCost": m.unit_cost,
        **record_meta(m),
    }
    if counts is not None:
        out["assetCounts"] = {"total": sum(counts.values()), "byStatus": counts}
    if full:
        out["specs"] = _specs(m)
        out["notes"] = m.notes
    return out


def _model_counts(actor) -> dict[int, dict[str, int]]:
    query = (select(Asset.model_id, Asset.status_code, func.count()).where(Asset.archived_at.is_(None))
             .group_by(Asset.model_id, Asset.status_code))
    scope = department_scope(actor)
    if scope is not ALL_DEPARTMENTS:
        query = query.where(Asset.department_id.in_(sorted(scope) or [-1]))
    out: dict[int, dict[str, int]] = {}
    for model_id, status, n in context.session().execute(query):
        out.setdefault(model_id, {})[status] = n
    return out


def list_models(actor, category_id: int | None = None, q: str | None = None, include_archived: bool = False) -> list:
    query = select(CapabilityModel)
    if not include_archived:
        query = query.where(CapabilityModel.archived_at.is_(None))
    if category_id:
        query = query.where(CapabilityModel.category_id == category_id)
    if q:
        pattern = repo.like_pattern(q)
        query = query.where(or_(func.lower(CapabilityModel.name_en).like(pattern, escape="\\"),
                                func.lower(CapabilityModel.name_ar).like(pattern, escape="\\"),
                                func.lower(CapabilityModel.code).like(pattern, escape="\\")))
    counts = _model_counts(actor)
    return [model_dto(m, counts.get(m.id, {})) for m in
            context.session().scalars(query.order_by(CapabilityModel.code))]


def get_model(actor, model_id: int) -> dict:
    model = crud.load(CapabilityModel, model_id, actor, "Model")
    out = model_dto(model, _model_counts(actor).get(model.id, {}), full=True)
    session = context.session()
    req_ids = session.scalars(select(RequirementModel.requirement_id)
                              .where(RequirementModel.model_id == model.id)).all()
    out["requirementIds"] = [sid(i) for i in req_ids]
    out["projectIds"] = [sid(i) for i in session.scalars(select(ProjectModel.project_id)
                                                         .where(ProjectModel.model_id == model.id))]
    return out


def _check_specs(category_id: int, specs: dict | None) -> str | None:
    if specs is None:
        return None
    fields = {f.code: f for f in context.session().scalars(
        select(SpecField).where(SpecField.category_id == category_id, SpecField.archived_at.is_(None)))}
    clean = {}
    for key, value in specs.items():
        field = fields.get(key)
        if field is None:
            raise ValidationFailed.field("specs", f"{key} is not a specification field of this category.")
        if value is None or value == "":
            continue
        if field.data_type == "NUMBER" and (not isinstance(value, (int, float)) or isinstance(value, bool)):
            raise ValidationFailed.field("specs", f"{key} must be a number.")
        if field.data_type == "BOOL" and not isinstance(value, bool):
            raise ValidationFailed.field("specs", f"{key} must be yes or no.")
        if field.data_type == "TEXT" and (not isinstance(value, str) or len(value) > 200):
            raise ValidationFailed.field("specs", f"{key} must be a text of at most 200 characters.")
        clean[key] = value
    encoded = json.dumps(clean, ensure_ascii=False, sort_keys=True)
    if len(encoded) > 4000:
        raise ValidationFailed.field("specs", "Too many specification values.")
    return encoded


_MODEL_FIELDS = ("name_en", "name_ar", "category_id", "manufacturer_id", "role_en", "role_ar", "unit_cost", "notes")


def create_model(actor, data) -> dict:
    crud.check_unique_code(CapabilityModel, data.code)
    crud.check_ref(CapabilityCategory, data.category_id, "categoryId", "Category")
    crud.check_ref(Organization, data.manufacturer_id, "manufacturerId", "Organization")
    model = CapabilityModel(code=data.code, **{k: getattr(data, k) for k in _MODEL_FIELDS},
                            specs_json=_check_specs(data.category_id, data.specs))
    crud.create(actor, model, PERM_EDIT_MODELS)
    return get_model(actor, model.id)


def update_model(actor, model_id: int, data) -> dict:
    model = crud.load(CapabilityModel, model_id, actor, "Model", for_update=True)
    changes = {k: v for k, v in data.changes().items() if k in _MODEL_FIELDS}
    if "category_id" in changes and changes["category_id"] != model.category_id:
        crud.check_ref(CapabilityCategory, changes["category_id"], "categoryId", "Category")
    if changes.get("manufacturer_id") not in (None, model.manufacturer_id):
        crud.check_ref(Organization, changes["manufacturer_id"], "manufacturerId", "Organization")
    if "specs" in data.model_fields_set:
        changes["specs_json"] = _check_specs(changes.get("category_id", model.category_id), data.specs)
    crud.update(actor, model, changes, PERM_EDIT_MODELS, data.version, data.reason)
    return get_model(actor, model.id)


def archive_model(actor, model_id: int, archived: bool, version: int | None, reason: str | None) -> dict:
    model = crud.load(CapabilityModel, model_id, actor, "Model", for_update=True)
    crud.set_archived(actor, model, archived, PERM_EDIT_MODELS, version, reason)
    return get_model(actor, model.id)


# ---------------------------------------------------------------- requirements -------------------------------------


def list_requirements(actor, department_id: int | None = None, category_id: int | None = None) -> list[dict]:
    return metrics_service.requirement_metrics(actor, department_id, category_id)


def get_requirement(actor, requirement_id: int) -> dict:
    req = crud.load(CapabilityRequirement, requirement_id, actor, "Requirement")
    rows = [r for r in metrics_service.requirement_metrics(actor) if r["id"] == sid(req.id)]
    out = rows[0] if rows else {"id": sid(req.id), "code": req.code, "nameEn": req.name_en, "nameAr": req.name_ar}
    models = lk.by_id(CapabilityModel)
    out.update({"targetDate": req.target_date.isoformat() if req.target_date else None, "notes": req.notes,
                "models": [lk.ref(models.get(i)) for i in req.model_ids if i in models], **record_meta(req)})
    return out


_REQ_FIELDS = ("name_en", "name_ar", "department_id", "category_id", "required_qty", "priority", "target_date", "notes")


def _check_model_ids(category_id: int, model_ids: list[int], keep: set[int] = frozenset()) -> list[int]:
    ids = list(dict.fromkeys(model_ids))
    for model_id in ids:
        model = crud.check_ref(CapabilityModel, model_id, "modelIds", "Model", allow_archived=model_id in keep)
        if model.category_id != category_id:
            raise ValidationFailed.field("modelIds", f"Model {model.code} is not in the requirement's category.")
    return ids


def _set_models(req: CapabilityRequirement, model_ids: list[int]) -> None:
    wanted = set(model_ids)
    req.model_links[:] = [link for link in req.model_links if link.model_id in wanted]
    have = {link.model_id for link in req.model_links}
    for model_id in model_ids:
        if model_id not in have:
            req.model_links.append(RequirementModel(model_id=model_id, created_at=context.now()))


def create_requirement(actor, data) -> dict:
    crud.check_unique_code(CapabilityRequirement, data.code)
    crud.check_ref(Department, data.department_id, "departmentId", "Department")
    crud.check_ref(CapabilityCategory, data.category_id, "categoryId", "Category")
    model_ids = _check_model_ids(data.category_id, data.model_ids)
    req = CapabilityRequirement(code=data.code, **{k: getattr(data, k) for k in _REQ_FIELDS})
    _set_models(req, model_ids)
    crud.create(actor, req, PERM_EDIT_REQUIREMENTS, data.department_id, commit=False)
    context.session().commit()
    return get_requirement(actor, req.id)


def update_requirement(actor, requirement_id: int, data) -> dict:
    req = crud.load(CapabilityRequirement, requirement_id, actor, "Requirement", for_update=True)
    changes = {k: v for k, v in data.changes().items() if k in _REQ_FIELDS}
    if changes.get("department_id") not in (None, req.department_id):
        crud.check_ref(Department, changes["department_id"], "departmentId", "Department")
    if changes.get("category_id") not in (None, req.category_id):
        crud.check_ref(CapabilityCategory, changes["category_id"], "categoryId", "Category")
    category_id = changes.get("category_id", req.category_id)
    model_ids = data.model_ids if data.model_ids is not None else req.model_ids
    model_ids = _check_model_ids(category_id, model_ids, set(req.model_ids))

    def links():
        return {"model_ids_text": ",".join(str(i) for i in sorted(req.model_ids)) or None}

    before_links = links()
    _set_models(req, model_ids)
    changed = crud.update(actor, req, changes, PERM_EDIT_REQUIREMENTS, data.version, data.reason,
                          department_ids=(req.department_id, changes.get("department_id", req.department_id)),
                          commit=False)
    if not changed and links() != before_links:
        # Only the model list changed: still one audited update with a version bump.
        before = {**audit_service.snapshot(req), **before_links}
        context.stamp_update(req, actor, context.now())
        req.updated_at = context.now()
        context.session().flush()
        audit_service.record(actor, "UPDATE", req, before, {**audit_service.snapshot(req), **links()}, data.reason)
    context.session().commit()
    return get_requirement(actor, req.id)


def archive_requirement(actor, requirement_id: int, archived: bool, version: int | None, reason: str | None) -> dict:
    req = crud.load(CapabilityRequirement, requirement_id, actor, "Requirement", for_update=True)
    crud.set_archived(actor, req, archived, PERM_EDIT_REQUIREMENTS, version, reason)
    return get_requirement(actor, req.id)
