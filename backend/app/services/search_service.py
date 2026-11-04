"""GET /search?q=: one search across capability models, assets (codes and serial numbers), requirements, projects and
contracts; later modules (tests, maintenance, documents) add their groups here. Department scope applies."""
from __future__ import annotations

from sqlalchemy import func, or_, select

from ..models import CapabilityRequirement, Contract, Department, Organization, Project
from ..repositories import common as repo
from ..schemas.dto import sid
from ..security.auth import ALL_DEPARTMENTS, department_scope
from . import asset_service, capability_service, context, lookup_service as lk

LIMIT = 25
_EXTRA_GROUPS = []


def register(group):
    """group(actor, q) -> (key, items): later modules add their search groups."""
    _EXTRA_GROUPS.append(group)


def _like(*columns, q: str):
    pattern = repo.like_pattern(q)
    return or_(*(func.lower(c).like(pattern, escape="\\") for c in columns))


def search(actor, q: str) -> dict:
    session = context.session()
    scope = department_scope(actor)
    out = {"q": q}
    out["models"] = capability_service.list_models(actor, q=q)[:LIMIT]
    out["assets"] = asset_service.list_assets(actor, {"q": q}, 0, LIMIT)["items"]
    req_q = select(CapabilityRequirement).where(CapabilityRequirement.archived_at.is_(None),
                                                _like(CapabilityRequirement.code, CapabilityRequirement.name_en,
                                                      CapabilityRequirement.name_ar, q=q))
    proj_q = select(Project).where(Project.archived_at.is_(None), _like(Project.code, Project.name_en, Project.name_ar, q=q))
    if scope is not ALL_DEPARTMENTS:
        req_q = req_q.where(CapabilityRequirement.department_id.in_(sorted(scope) or [-1]))
        proj_q = proj_q.where(Project.department_id.in_(sorted(scope) or [-1]))
    out["requirements"] = [{"id": sid(r.id), "code": r.code, "nameEn": r.name_en, "nameAr": r.name_ar,
                            "department": lk.ref_id(Department, r.department_id)}
                           for r in session.scalars(req_q.order_by(CapabilityRequirement.code).limit(LIMIT))]
    out["projects"] = [{"id": sid(p.id), "code": p.code, "nameEn": p.name_en, "nameAr": p.name_ar,
                        "status": p.status_code} for p in session.scalars(proj_q.order_by(Project.code).limit(LIMIT))]
    contract_q = select(Contract).where(Contract.archived_at.is_(None),
                                        _like(Contract.code, Contract.title_en, Contract.title_ar, q=q))
    out["contracts"] = [{"id": sid(c.id), "code": c.code, "titleEn": c.title_en, "titleAr": c.title_ar,
                         "supplier": lk.ref_id(Organization, c.supplier_id)}
                        for c in session.scalars(contract_q.order_by(Contract.code).limit(LIMIT))]
    for group in _EXTRA_GROUPS:
        key, items = group(actor, q)
        out[key] = items
    return out
