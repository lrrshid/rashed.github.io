"""GET /lookups: every configurable list the browser needs for labels, filters and forms, in one small answer.
Also small per-request caches of the lists for the services (names in DTOs, status checks)."""
from __future__ import annotations

from flask import g, has_request_context
from sqlalchemy import select

from ..models import (AppRole, CapabilityCategory, CapabilityModel, Contract, Department, Organization, ProjectType,
                      Site, SpecField, StatusDef, WorkflowStage)
from ..schemas.dto import sid
from . import context


def _cached(name: str, loader):
    if not has_request_context():
        return loader()
    store = g.__dict__.setdefault("_lookup_cache", {})
    if name not in store:
        store[name] = loader()
    return store[name]


def by_id(model) -> dict:
    return _cached(model.__tablename__, lambda: {e.id: e for e in context.session().scalars(select(model))})


def statuses(domain: str) -> dict[str, StatusDef]:
    def load():
        rows = context.session().scalars(select(StatusDef).where(StatusDef.domain == domain)
                                         .order_by(StatusDef.sort_order, StatusDef.id))
        return {s.code: s for s in rows}
    return _cached(f"status:{domain}", load)


def ref(entity, with_code: bool = True) -> dict | None:
    """{id, code, nameEn, nameAr} of a list entry or record, for DTOs."""
    if entity is None:
        return None
    out = {"id": sid(entity.id), "nameEn": entity.name_en, "nameAr": entity.name_ar}
    if with_code and hasattr(entity, "code"):
        out["code"] = entity.code
    return out


def ref_id(model, entity_id: int | None) -> dict | None:
    return ref(by_id(model).get(entity_id)) if entity_id is not None else None


def _list(model, order=None):
    rows = context.session().scalars(select(model).order_by(*(order or (model.sort_order, model.id))))
    return rows.all()


def _entry(e, **extra) -> dict:
    out = {"id": sid(e.id), "code": getattr(e, "code", None), "nameEn": e.name_en, "nameAr": e.name_ar,
           "sortOrder": getattr(e, "sort_order", 0), "archived": getattr(e, "archived_at", None) is not None,
           "version": e.version}
    out.update(extra)
    return out


def lookups() -> dict:
    stages_by_type: dict[int, list] = {}
    for stage in _list(WorkflowStage, (WorkflowStage.project_type_id, WorkflowStage.sort_order, WorkflowStage.id)):
        stages_by_type.setdefault(stage.project_type_id, []).append(_entry(stage))
    status_rows = context.session().scalars(select(StatusDef).order_by(StatusDef.domain, StatusDef.sort_order,
                                                                       StatusDef.id))
    status_map: dict[str, list] = {}
    for s in status_rows:
        status_map.setdefault(s.domain, []).append(
            _entry(s, color=s.color, terminal=bool(s.is_terminal)))
    return {
        "departments": [_entry(d) for d in _list(Department)],
        "categories": [_entry(c) for c in _list(CapabilityCategory)],
        "sites": [_entry(s) for s in _list(Site)],
        "organizations": [_entry(o, kind=o.kind, countryEn=o.country_en, countryAr=o.country_ar)
                          for o in _list(Organization)],
        "statuses": status_map,
        "projectTypes": [_entry(t, color=t.color, stages=stages_by_type.get(t.id, [])) for t in _list(ProjectType)],
        "specFields": [_entry(f, categoryId=sid(f.category_id), section=f.section, unit=f.unit, dataType=f.data_type,
                              custom=bool(f.is_custom))
                       for f in _list(SpecField, (SpecField.category_id, SpecField.sort_order, SpecField.id))],
        "models": [_entry(m, category={"id": sid(m.category_id)}) for m in
                   _list(CapabilityModel, (CapabilityModel.code, CapabilityModel.id))],
        "contracts": [{"id": sid(c.id), "code": c.code, "nameEn": c.title_en, "nameAr": c.title_ar,
                       "archived": c.archived_at is not None}
                      for c in _list(Contract, (Contract.code, Contract.id))],
        "roles": [{"code": r.code, "nameEn": r.name_en, "nameAr": r.name_ar, "scope": r.scope}
                  for r in context.session().scalars(select(AppRole).order_by(AppRole.sort_order, AppRole.id))],
    }
