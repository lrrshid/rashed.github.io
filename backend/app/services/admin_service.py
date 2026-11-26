"""Settings: the configurable lists (departments, categories, sites, organisations, statuses, project types and
their workflow stages, specification fields, AI technologies, contracts) and the roles with their permissions.
System administrators only. Everything is audited; list entries are archived, never deleted."""
from __future__ import annotations

from sqlalchemy import func, select

from ..exceptions import Conflict, NotFound, ValidationFailed
from ..models import (AiTechnology, AppRole, AppUser, CapabilityCategory, Contract, Department, Organization,
                      OrgUnit, ProjectType, RolePermission, Site, SpecField, StatusDef, WorkflowStage)
from ..models.lists import COLORS, SPEC_SECTIONS, SPEC_TYPES, STATUS_DOMAINS
from ..schemas.dto import record_meta, sid
from ..security.auth import PERMISSIONS, require_admin
from . import audit_service, context, crud

CODE_UPPER = r"^[A-Z0-9_-]{1,30}$"

# kind -> (model, editable fields {api name: (attribute, type)}, required on create, order)
_TEXT = "text"
_INT = "int"
_BOOL = "bool"
LISTS = {
    "departments": (Department, {"code": ("code", "code"), "nameEn": ("name_en", _TEXT), "nameAr": ("name_ar", _TEXT),
                                 "sortOrder": ("sort_order", _INT)}),
    "categories": (CapabilityCategory, {"code": ("code", "code"), "nameEn": ("name_en", _TEXT), "nameAr": ("name_ar", _TEXT),
                                        "sortOrder": ("sort_order", _INT)}),
    "sites": (Site, {"code": ("code", "code"), "nameEn": ("name_en", _TEXT), "nameAr": ("name_ar", _TEXT),
                     "sortOrder": ("sort_order", _INT)}),
    # Directorates (no parent) and their sections (parent = a directorate): the units that conduct tests.
    "units": (OrgUnit, {"code": ("code", "code"), "nameEn": ("name_en", _TEXT), "nameAr": ("name_ar", _TEXT),
                        "parentId": ("parent_id", "ref:OrgUnit"), "sortOrder": ("sort_order", _INT)}),
    "organizations": (Organization, {"code": ("code", "code"), "nameEn": ("name_en", _TEXT), "nameAr": ("name_ar", _TEXT),
                                     "kind": ("kind", ("MANUFACTURER", "SUPPLIER", "BOTH")),
                                     "countryEn": ("country_en", _TEXT), "countryAr": ("country_ar", _TEXT),
                                     "sortOrder": ("sort_order", _INT)}),
    "statuses": (StatusDef, {"domain": ("domain", STATUS_DOMAINS), "code": ("code", "code"), "nameEn": ("name_en", _TEXT),
                             "nameAr": ("name_ar", _TEXT), "color": ("color", COLORS), "terminal": ("is_terminal", _BOOL),
                             "sortOrder": ("sort_order", _INT)}),
    "projectTypes": (ProjectType, {"code": ("code", "code"), "nameEn": ("name_en", _TEXT), "nameAr": ("name_ar", _TEXT),
                                   "color": ("color", COLORS), "sortOrder": ("sort_order", _INT)}),
    "stages": (WorkflowStage, {"projectTypeId": ("project_type_id", "ref:ProjectType"), "nameEn": ("name_en", _TEXT),
                               "nameAr": ("name_ar", _TEXT), "sortOrder": ("sort_order", _INT)}),
    "specFields": (SpecField, {"categoryId": ("category_id", "ref:CapabilityCategory"), "section": ("section", SPEC_SECTIONS),
                               "code": ("code", "lower"), "nameEn": ("name_en", _TEXT), "nameAr": ("name_ar", _TEXT),
                               "unit": ("unit", _TEXT), "dataType": ("data_type", SPEC_TYPES), "sortOrder": ("sort_order", _INT)}),
    "aiTechnologies": (AiTechnology, {"code": ("code", "code"), "nameEn": ("name_en", _TEXT), "nameAr": ("name_ar", _TEXT),
                                      "sortOrder": ("sort_order", _INT)}),
    "contracts": (Contract, {"code": ("code", "code"), "titleEn": ("title_en", _TEXT), "titleAr": ("title_ar", _TEXT),
                             "supplierId": ("supplier_id", "ref:Organization"), "contractValue": ("contract_value", "money"),
                             "startDate": ("start_date", "date"), "endDate": ("end_date", "date")}),
}
_REFS = {"ProjectType": ProjectType, "CapabilityCategory": CapabilityCategory, "Organization": Organization,
         "OrgUnit": OrgUnit}
_REQUIRED = {"departments": ("code", "nameEn", "nameAr"), "categories": ("code", "nameEn", "nameAr"),
             "sites": ("code", "nameEn", "nameAr"), "units": ("code", "nameEn", "nameAr"),
             "organizations": ("code", "nameEn", "nameAr", "kind"),
             "statuses": ("domain", "code", "nameEn", "nameAr"), "projectTypes": ("code", "nameEn", "nameAr"),
             "stages": ("projectTypeId", "nameEn", "nameAr"), "specFields": ("categoryId", "section", "code", "nameEn", "nameAr", "dataType"),
             "aiTechnologies": ("code", "nameEn", "nameAr"), "contracts": ("code", "titleEn", "titleAr")}
# Codes that the system relies on are fixed once created (statuses are referenced by records; categories by codes).
_CODE_FIXED = {"statuses", "categories", "departments", "specFields", "aiTechnologies"}


def _spec(kind: str):
    if kind not in LISTS:
        raise NotFound(f"There is no list called {kind}.")
    return LISTS[kind]


def _dto(kind: str, e) -> dict:
    _, fields = _spec(kind)
    out = {"id": sid(e.id)}
    for api_name, (attr, ftype) in fields.items():
        value = getattr(e, attr)
        if ftype == _BOOL:
            value = bool(value)
        elif isinstance(ftype, str) and ftype.startswith("ref:"):
            value = sid(value)
        elif hasattr(value, "isoformat"):
            value = value.isoformat()
        out[api_name] = value
    out.update(record_meta(e))
    return out


def list_entries(actor, kind: str) -> list[dict]:
    require_admin(actor)
    model, _ = _spec(kind)
    order = [getattr(model, c) for c in ("project_type_id", "category_id", "domain", "sort_order", "code") if hasattr(model, c)]
    return [_dto(kind, e) for e in context.session().scalars(select(model).order_by(*order, model.id))]


def _parse(kind: str, payload: dict, creating: bool) -> dict:
    import re
    from datetime import date
    _, fields = _spec(kind)
    unknown = set(payload) - set(fields) - {"version", "reason"}
    if unknown:
        raise ValidationFailed("Unsupported field.", [{"field": f, "message": "Unsupported field."} for f in sorted(unknown)])
    out = {}
    for api_name, (attr, ftype) in fields.items():
        if api_name not in payload:
            continue
        v = payload[api_name]
        if isinstance(v, str):
            v = v.strip()
            if v == "":
                v = None
        if v is None:
            if creating and api_name in _REQUIRED[kind] or (not creating and api_name in _REQUIRED[kind]):
                raise ValidationFailed.field(api_name, "This field is required.")
            out[attr] = None
            continue
        if ftype == "code":
            v = str(v).upper()
            if not re.fullmatch(CODE_UPPER, v):
                raise ValidationFailed.field(api_name, "Use capital letters, digits, - and _ only.")
        elif ftype == "lower":
            v = str(v).lower()
            if not re.fullmatch(r"^[a-z0-9_]{2,40}$", v):
                raise ValidationFailed.field(api_name, "Use small letters, digits and _ only.")
        elif ftype == _TEXT:
            if not isinstance(v, str) or len(v) > 200:
                raise ValidationFailed.field(api_name, "Must be a text of at most 200 characters.")
        elif ftype == _INT:
            if isinstance(v, bool) or not isinstance(v, int) or not -10000 <= v <= 10000:
                raise ValidationFailed.field(api_name, "Must be a whole number.")
        elif ftype == "money":
            if isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0:
                raise ValidationFailed.field(api_name, "Must be an amount of 0 or more.")
        elif ftype == _BOOL:
            if not isinstance(v, bool):
                raise ValidationFailed.field(api_name, "Must be true or false.")
            v = 1 if v else 0
        elif ftype == "date":
            try:
                v = date.fromisoformat(str(v))
            except ValueError:
                raise ValidationFailed.field(api_name, "Use the date format YYYY-MM-DD.") from None
        elif isinstance(ftype, str) and ftype.startswith("ref:"):
            try:
                v = int(v)
            except (TypeError, ValueError):
                raise ValidationFailed.field(api_name, "Must be an id.") from None
            crud.check_ref(_REFS[ftype[4:]], v, api_name, ftype[4:])
        elif isinstance(ftype, tuple):
            v = str(v).upper() if ftype is not COLORS else str(v).lower()
            if v not in ftype:
                raise ValidationFailed.field(api_name, f"Must be one of: {', '.join(ftype)}.")
        out[attr] = v
    if creating:
        missing = [f for f in _REQUIRED[kind] if fields[f][0] not in out]
        if missing:
            raise ValidationFailed("Please correct the highlighted fields.",
                                   [{"field": f, "message": "This field is required."} for f in missing])
    return out


def _check_unique(kind: str, model, values: dict, exclude_id: int | None = None) -> None:
    if "code" not in values:
        return
    query = select(model.id).where(func.upper(model.code) == values["code"].upper())
    if kind == "statuses":
        query = query.where(model.domain == values.get("domain"))
    if kind == "specFields":
        query = query.where(model.category_id == values.get("category_id"))
    if exclude_id is not None:
        query = query.where(model.id != exclude_id)
    if context.session().scalar(query) is not None:
        raise ValidationFailed.field("code", f"{values['code']} is already used.")


def _check_unit_parent(unit: OrgUnit | None, parent_id: int | None) -> None:
    """Two levels: a section's parent is a directorate (a unit without a parent), and a directorate that has sections
    cannot itself become a section."""
    if parent_id is None:
        return
    session = context.session()
    parent = session.get(OrgUnit, parent_id)
    if unit is not None and parent_id == unit.id:
        raise ValidationFailed.field("parentId", "A unit cannot be its own directorate.")
    if parent.parent_id is not None:
        raise ValidationFailed.field("parentId", "Choose a directorate (a unit without a directorate of its own).")
    if unit is not None and session.scalar(select(OrgUnit.id).where(OrgUnit.parent_id == unit.id).limit(1)) is not None:
        raise ValidationFailed.field("parentId",
                                     "This directorate has sections, so it cannot belong to another directorate.")


def create_entry(actor, kind: str, payload: dict) -> dict:
    require_admin(actor)
    model, _ = _spec(kind)
    values = _parse(kind, payload, creating=True)
    if kind == "specFields":
        values["is_custom"] = 1
    if kind == "stages" and "sort_order" not in values:
        last = context.session().scalar(select(func.max(WorkflowStage.sort_order)).where(
            WorkflowStage.project_type_id == values["project_type_id"]))
        values["sort_order"] = (last or 0) + 1
    _check_unique(kind, model, values)
    if kind == "units":
        _check_unit_parent(None, values.get("parent_id"))
    entity = model(**values)
    crud.create(actor, entity, "admin", reason=payload.get("reason"))
    return _dto(kind, entity)


def update_entry(actor, kind: str, entry_id: int, payload: dict) -> dict:
    require_admin(actor)
    model, _ = _spec(kind)
    entity = crud.load(model, entry_id, actor, "Entry", for_update=True, department_of=lambda e: None)
    values = _parse(kind, payload, creating=False)
    if kind in _CODE_FIXED and "code" in values and values["code"] != entity.code:
        raise Conflict("This code is used by records and cannot change. Archive the entry and add a new one.",
                       code="CODE_FIXED")
    for fixed in ("domain", "category_id", "project_type_id"):
        if fixed in values and values[fixed] != getattr(entity, fixed):
            raise Conflict("This entry cannot move to another list.", code="CODE_FIXED")
    if kind == "units" and "parent_id" in values:
        _check_unit_parent(entity, values["parent_id"])
    if "code" in values:
        _check_unique(kind, model, {**{"domain": getattr(entity, "domain", None),
                                       "category_id": getattr(entity, "category_id", None)}, **values}, entity.id)
    crud.update(actor, entity, values, "admin", payload.get("version"), payload.get("reason"), department_ids=(None,))
    return _dto(kind, entity)


def archive_entry(actor, kind: str, entry_id: int, archived: bool, version, reason) -> dict:
    require_admin(actor)
    model, _ = _spec(kind)
    entity = crud.load(model, entry_id, actor, "Entry", for_update=True, department_of=lambda e: None)
    crud.set_archived(actor, entity, archived, "admin", version, reason)
    return _dto(kind, entity)


def reorder_stages(actor, project_type_id: int, stage_ids: list[int]) -> list[dict]:
    """Workflow stages of one project type in a new order (the whole list)."""
    require_admin(actor)
    session = context.session()
    stages = {s.id: s for s in session.scalars(select(WorkflowStage).where(WorkflowStage.project_type_id == project_type_id))}
    if set(stage_ids) != set(stages):
        raise ValidationFailed.field("stageIds", "Send every stage of the project type exactly once.")
    for order, sid_ in enumerate(stage_ids, start=1):
        stage = stages[sid_]
        if stage.sort_order != order:
            crud.update(actor, stage, {"sort_order": order}, "admin", None, "Workflow reordered", department_ids=(None,),
                        commit=False)
    session.commit()
    return [s for s in list_entries(actor, "stages") if s["projectTypeId"] == sid(project_type_id)]


# ---------------------------------------------------------------- roles --------------------------------------------


def role_dto(role: AppRole) -> dict:
    users = context.session().scalar(select(func.count()).select_from(AppUser).where(AppUser.role_code == role.code,
                                                                                     AppUser.is_active == 1))
    return {"id": sid(role.id), "code": role.code, "nameEn": role.name_en, "nameAr": role.name_ar, "scope": role.scope,
            "tier": role.tier, "system": bool(role.is_system), "permissions": sorted(role.permissions),
            "activeUsers": users, "version": role.version}


def list_roles(actor) -> dict:
    require_admin(actor)
    roles = context.session().scalars(select(AppRole).order_by(AppRole.sort_order, AppRole.id))
    return {"items": [role_dto(r) for r in roles], "permissions": list(PERMISSIONS)}


def save_role(actor, payload: dict, role_id: int | None = None) -> dict:
    import re
    require_admin(actor)
    session = context.session()
    allowed = {"code", "nameEn", "nameAr", "scope", "tier", "permissions", "version", "reason"}
    unknown = set(payload) - allowed
    if unknown:
        raise ValidationFailed("Unsupported field.", [{"field": f, "message": "Unsupported field."} for f in sorted(unknown)])
    perms = payload.get("permissions")
    if perms is not None:
        if not isinstance(perms, list) or any(p not in PERMISSIONS for p in perms):
            raise ValidationFailed.field("permissions", "Unknown permission.")
        perms = sorted(set(perms))
    scope = payload.get("scope")
    if scope is not None and scope not in ("ALL", "DEPARTMENT"):
        raise ValidationFailed.field("scope", "Must be ALL or DEPARTMENT.")
    for key in ("nameEn", "nameAr"):
        if key in payload and not (isinstance(payload[key], str) and 2 <= len(payload[key].strip()) <= 120):
            raise ValidationFailed.field(key, "Must be 2 to 120 characters.")
    # The level in the organisation's hierarchy (1 = top, 0 = not placed): shown in Settings > Roles, grants nothing.
    tier = payload.get("tier")
    if tier is not None and (isinstance(tier, bool) or not isinstance(tier, int) or not 0 <= tier <= 20):
        raise ValidationFailed.field("tier", "Must be a whole number from 0 to 20.")
    now = context.now()
    if role_id is None:
        code = str(payload.get("code") or "").strip().upper()
        if not re.fullmatch(r"^[A-Z0-9_]{2,30}$", code):
            raise ValidationFailed.field("code", "Use capital letters, digits and _ (2 to 30).")
        if session.scalar(select(AppRole.id).where(AppRole.code == code)) is not None:
            raise ValidationFailed.field("code", f"{code} is already used.")
        if not payload.get("nameEn") or not payload.get("nameAr"):
            raise ValidationFailed.field("nameEn", "Both names are required.")
        role = AppRole(code=code, name_en=payload["nameEn"].strip(), name_ar=payload["nameAr"].strip(),
                       scope=scope or "ALL", is_system=0, sort_order=100, tier=tier or 0, created_at=now, updated_at=now)
        role.permission_links = [RolePermission(permission=p, created_at=now) for p in (perms or ["view"])]
        session.add(role)
        session.flush()
        audit_service.record(actor, "CREATE", role, None, {**audit_service.snapshot(role),
                                                           "permissions": ",".join(role.permissions)})
        session.commit()
        return role_dto(role)
    role = session.get(AppRole, role_id)
    if role is None:
        raise NotFound(f"Role {role_id} was not found.")
    if payload.get("version") is not None:
        context.check_version(role, payload["version"])
    if role.is_system and perms is not None and "admin" not in perms:
        raise Conflict("The system administrator role keeps every permission.", code="SYSTEM_ROLE")
    if scope is not None and scope != role.scope:
        users = session.scalar(select(func.count()).select_from(AppUser).where(AppUser.role_code == role.code))
        if users:
            raise Conflict("Change the scope only for a role nobody has; create a new role instead.", code="ROLE_IN_USE")
    before = {**audit_service.snapshot(role), "permissions": ",".join(sorted(role.permissions))}
    if "nameEn" in payload:
        role.name_en = payload["nameEn"].strip()
    if "nameAr" in payload:
        role.name_ar = payload["nameAr"].strip()
    if scope is not None:
        role.scope = scope
    if tier is not None:
        role.tier = tier
    if perms is not None:
        role.permission_links[:] = [link for link in role.permission_links if link.permission in perms]
        have = {link.permission for link in role.permission_links}
        for p in perms:
            if p not in have:
                role.permission_links.append(RolePermission(permission=p, created_at=now))
    after = {**audit_service.snapshot(role), "permissions": ",".join(sorted(perms if perms is not None else role.permissions))}
    if after != before:
        role.updated_at = now
        session.flush()
        after["version"] = role.version
        audit_service.record(actor, "UPDATE", role, before, after, payload.get("reason"))
    session.commit()
    return role_dto(role)
