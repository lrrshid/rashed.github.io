"""Audit history, business-rule settings, saved views, and the history of one record."""
from __future__ import annotations

import json

from flask import jsonify, request
from sqlalchemy import select

from ...exceptions import NotFound, ValidationFailed
from ...models import Asset, CapabilityModel, CapabilityRequirement, SavedView
from ...schemas.common import ApiModel, Query, Reason, Version, required_text
from ...security.auth import PERM_VIEW, admin_only, permission_required
from ...services import audit_service, context, crud, settings_service
from . import body, bp, created, user

# Record types whose history any user who may see the record can read (the record's own scope check applies).
_HISTORY = {"ASSET": (Asset, "Asset"), "CAPABILITY_MODEL": (CapabilityModel, "Model"),
            "CAPABILITY_REQUIREMENT": (CapabilityRequirement, "Requirement")}


def register_history(entity_type: str, model, what: str, department_of=None) -> None:
    _HISTORY[entity_type] = (model, what, department_of) if department_of else (model, what)


@bp.get("/audit")
@admin_only
def audit_events():
    query = Query(request.args, {"entityType", "entityId"})
    page, size = query.page()
    kind = query.text("entityType", 30)
    return jsonify(audit_service.list_events(page, size, kind.upper() if kind else None, query.id("entityId")))


@bp.get("/history/<entity_type>/<int:entity_id>")
@permission_required(PERM_VIEW)
def record_history(entity_type: str, entity_id: int):
    Query(request.args, set())
    spec = _HISTORY.get(entity_type.upper())
    if spec is None:
        raise NotFound("No history for that kind of record.")
    model, what, *rest = spec
    crud.load(model, entity_id, user(), what, department_of=rest[0] if rest else None)
    return jsonify({"items": audit_service.entity_history(entity_type.upper(), entity_id)})


@bp.get("/settings")
@permission_required(PERM_VIEW)
def get_settings():
    Query(request.args, set())
    return jsonify({"items": settings_service.all_settings()})


class SettingUpdate(ApiModel):
    value: object
    version: int | None = None  # 0 for a rule that still has its default (never saved)
    reason: Reason = None


@bp.put("/settings/<key>")
@admin_only
def put_setting(key: str):
    data = SettingUpdate.model_validate(body())
    return jsonify(settings_service.update(user(), key, data.value, data.version, data.reason))


# ---------------------------------------------------------------- saved views --------------------------------------


class SavedViewCreate(ApiModel):
    page: required_text(2, 40)
    name: required_text(1, 80)
    filters: dict


def _view_dto(v: SavedView) -> dict:
    return {"id": str(v.id), "page": v.page, "name": v.name, "filters": json.loads(v.filters_json)}


@bp.get("/saved-views")
@permission_required(PERM_VIEW)
def list_saved_views():
    query = Query(request.args, {"page"})
    stmt = select(SavedView).where(SavedView.user_id == user().id)
    page = query.text("page", 40)
    if page:
        stmt = stmt.where(SavedView.page == page)
    return jsonify({"items": [_view_dto(v) for v in context.session().scalars(stmt.order_by(SavedView.name))]})


@bp.post("/saved-views")
@permission_required(PERM_VIEW)
def create_saved_view():
    data = SavedViewCreate.model_validate(body())
    encoded = json.dumps(data.filters, ensure_ascii=False, sort_keys=True)
    if len(encoded) > 4000:
        raise ValidationFailed.field("filters", "Too many filters.")
    session = context.session()
    count = len(session.scalars(select(SavedView.id).where(SavedView.user_id == user().id)).all())
    if count >= 50:
        raise ValidationFailed.field("name", "You have 50 saved views; delete one first.")
    view = SavedView(user_id=user().id, page=data.page, name=data.name, filters_json=encoded,
                     created_at=context.now())
    session.add(view)
    session.commit()
    return created(_view_dto(view), f"/api/v1/saved-views/{view.id}")


@bp.delete("/saved-views/<int:view_id>")
@permission_required(PERM_VIEW)
def delete_saved_view(view_id: int):
    session = context.session()
    view = session.get(SavedView, view_id)
    if view is None or view.user_id != user().id:
        raise NotFound("Saved view was not found.")
    session.delete(view)
    session.commit()
    return "", 204
