"""Every capability figure is computed here from the source records, never typed in.

Definitions (statuses per Settings > Business rules):
  available     assets of a requirement's models, in the requirement's department, in an "available" status
  operational   the same, in an "operational" status
  pipeline      the same, in a pipeline status (under acquisition / development / test)
  required      the requirement's quantity
  current %     min(available, required) / required
  forecast add  quantities that projects in a forecast status deliver toward the requirement (PROJECT_REQUIREMENT)
  forecast %    min(available + forecast add, required) / required
  gap           max(required - available, 0)
  forecast gap  max(required - available - forecast add, 0)
  critical gap  a CRITICAL or HIGH priority requirement whose forecast still leaves a gap (no approved project
                closes it)

Each figure carries `drill`: the asset filters (api/v1/assets.py) that list exactly the records behind it.
"""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import func, select

from ..models import (Asset, CapabilityCategory, CapabilityModel, CapabilityRequirement, Department, Project,
                      ProjectRequirement, RequirementModel)
from ..schemas.dto import sid
from ..security.auth import ALL_DEPARTMENTS, department_scope
from . import context, lookup_service as lk, settings_service


def _pct(part: float, whole: float) -> int | None:
    return None if not whole else round(100 * min(part, whole) / whole)


def _scope_ids(actor):
    scope = department_scope(actor)
    return None if scope is ALL_DEPARTMENTS else scope


def asset_status_counts(actor, department_id: int | None = None, category_id: int | None = None) -> dict[str, int]:
    """Non-archived assets in scope, by status."""
    query = (select(Asset.status_code, func.count()).join(CapabilityModel, CapabilityModel.id == Asset.model_id)
             .where(Asset.archived_at.is_(None)).group_by(Asset.status_code))
    scope = _scope_ids(actor)
    if scope is not None:
        query = query.where(Asset.department_id.in_(sorted(scope) or [-1]))
    if department_id:
        query = query.where(Asset.department_id == department_id)
    if category_id:
        query = query.where(CapabilityModel.category_id == category_id)
    return {code: n for code, n in context.session().execute(query)}


def _asset_tally(actor) -> dict:
    """(model_id, department_id, status) -> count, non-archived assets in scope."""
    query = (select(Asset.model_id, Asset.department_id, Asset.status_code, func.count())
             .where(Asset.archived_at.is_(None)).group_by(Asset.model_id, Asset.department_id, Asset.status_code))
    scope = _scope_ids(actor)
    if scope is not None:
        query = query.where(Asset.department_id.in_(sorted(scope) or [-1]))
    return {(m, d, s): n for m, d, s, n in context.session().execute(query)}


def requirement_metrics(actor, department_id: int | None = None, category_id: int | None = None) -> list[dict]:
    session = context.session()
    available = set(settings_service.get("assets.available_statuses"))
    operational = set(settings_service.get("assets.operational_statuses"))
    pipeline = list(settings_service.get("assets.pipeline_statuses"))
    forecast_statuses = set(settings_service.get("projects.forecast_statuses"))

    query = select(CapabilityRequirement).where(CapabilityRequirement.archived_at.is_(None))
    scope = _scope_ids(actor)
    if scope is not None:
        query = query.where(CapabilityRequirement.department_id.in_(sorted(scope) or [-1]))
    if department_id:
        query = query.where(CapabilityRequirement.department_id == department_id)
    if category_id:
        query = query.where(CapabilityRequirement.category_id == category_id)
    requirements = session.scalars(query.order_by(CapabilityRequirement.code)).all()
    tally = _asset_tally(actor)

    links: dict[int, list[int]] = defaultdict(list)
    for req_id, model_id in session.execute(select(RequirementModel.requirement_id, RequirementModel.model_id)):
        links[req_id].append(model_id)
    project_rows = session.execute(
        select(ProjectRequirement.requirement_id, ProjectRequirement.quantity, Project)
        .join(Project, Project.id == ProjectRequirement.project_id).where(Project.archived_at.is_(None))).all()
    projects_by_req: dict[int, list] = defaultdict(list)
    for req_id, qty, project in project_rows:
        projects_by_req[req_id].append((qty, project))

    out = []
    for r in requirements:
        counts: dict[str, int] = defaultdict(int)
        for model_id in links.get(r.id, []):
            for (m, d, s), n in tally.items():
                if m == model_id and d == r.department_id:
                    counts[s] += n
        avail = sum(n for s, n in counts.items() if s in available)
        oper = sum(n for s, n in counts.items() if s in operational)
        pipe = {s: counts.get(s, 0) for s in pipeline}
        forecast_projects = [(q, p) for q, p in projects_by_req.get(r.id, []) if p.status_code in forecast_statuses]
        forecast_add = sum(q for q, _ in forecast_projects)
        gap = max(r.required_qty - avail, 0)
        forecast_gap = max(r.required_qty - avail - forecast_add, 0)
        closure_dates = [p.forecast_end_date or p.target_end_date for _, p in forecast_projects
                         if (p.forecast_end_date or p.target_end_date)]
        out.append({
            "id": sid(r.id), "code": r.code, "nameEn": r.name_en, "nameAr": r.name_ar,
            "department": lk.ref_id(Department, r.department_id),
            "category": lk.ref_id(CapabilityCategory, r.category_id),
            "priority": r.priority,
            "required": r.required_qty, "available": avail, "operational": oper, "pipeline": pipe,
            "pipelineTotal": sum(pipe.values()), "forecastAdd": forecast_add,
            "currentPct": _pct(avail, r.required_qty), "forecastPct": _pct(avail + forecast_add, r.required_qty),
            "gap": gap, "forecastGap": forecast_gap,
            "critical": gap > 0 and forecast_gap > 0 and r.priority in ("CRITICAL", "HIGH"),
            "projects": [{"id": sid(p.id), "code": p.code, "nameEn": p.name_en, "nameAr": p.name_ar,
                          "status": p.status_code, "quantity": q,
                          "countsInForecast": p.status_code in forecast_statuses}
                         for q, p in projects_by_req.get(r.id, [])],
            "closureDate": max(closure_dates).isoformat() if closure_dates and forecast_gap == 0 else None,
            "drill": {"requirement": [sid(r.id)]},
        })
    return out


def _sum(rows: list[dict]) -> dict:
    required = sum(r["required"] for r in rows)
    available = sum(min(r["available"], r["required"]) for r in rows)
    forecast = sum(min(r["available"] + r["forecastAdd"], r["required"]) for r in rows)
    pipeline: dict[str, int] = defaultdict(int)
    for r in rows:
        for s, n in r["pipeline"].items():
            pipeline[s] += n
    return {
        "required": required,
        "available": sum(r["available"] for r in rows),
        "operational": sum(r["operational"] for r in rows),
        "pipeline": dict(pipeline), "pipelineTotal": sum(pipeline.values()),
        "forecastAdd": sum(r["forecastAdd"] for r in rows),
        "currentPct": _pct(available, required), "forecastPct": _pct(forecast, required),
        "gap": sum(r["gap"] for r in rows), "forecastGap": sum(r["forecastGap"] for r in rows),
        "criticalGaps": sum(1 for r in rows if r["critical"]),
        "requirements": len(rows),
    }


def completion(actor, by: str = "department") -> dict:
    """Totals plus one group per department (or category), from requirement_metrics."""
    rows = requirement_metrics(actor)
    groups = []
    if by == "department":
        entries = [d for d in lk.by_id(Department).values() if d.archived_at is None]
        key = "department"
    else:
        entries = [c for c in lk.by_id(CapabilityCategory).values() if c.archived_at is None]
        key = "category"
    scope = _scope_ids(actor)
    for e in sorted(entries, key=lambda e: (e.sort_order, e.id)):
        if key == "department" and scope is not None and e.id not in scope:
            continue
        mine = [r for r in rows if r[key]["id"] == sid(e.id)]
        groups.append({key: lk.ref(e), **_sum(mine), "drill": _drill(mine)})
    return {"total": {**_sum(rows), "drill": _drill(rows)}, "groups": groups, "requirements": rows}


def _drill(rows: list[dict]) -> dict:
    """The assets behind a group of requirements: the requirements' models in the requirements' departments."""
    return {"requirement": [r["id"] for r in rows], "statusGroup": "AVAILABLE"} if rows else None


def gap_heatmap(actor, forecast: bool = False) -> dict:
    """Department x category: the summed (current or forecast) gap, required and available per cell."""
    rows = requirement_metrics(actor)
    departments = sorted((d for d in lk.by_id(Department).values() if d.archived_at is None),
                         key=lambda e: (e.sort_order, e.id))
    scope = _scope_ids(actor)
    if scope is not None:
        departments = [d for d in departments if d.id in scope]
    categories = sorted((c for c in lk.by_id(CapabilityCategory).values() if c.archived_at is None),
                        key=lambda e: (e.sort_order, e.id))
    field = "forecastGap" if forecast else "gap"
    cells = []
    for d in departments:
        for c in categories:
            mine = [r for r in rows if r["department"]["id"] == sid(d.id) and r["category"]["id"] == sid(c.id)]
            cells.append({"departmentId": sid(d.id), "categoryId": sid(c.id),
                          "gap": sum(r[field] for r in mine) if mine else None,
                          "required": sum(r["required"] for r in mine), "available": sum(r["available"] for r in mine),
                          "critical": any(r["critical"] for r in mine),
                          "drill": _drill(mine)})
    return {"departments": [lk.ref(d) for d in departments], "categories": [lk.ref(c) for c in categories],
            "cells": cells, "forecast": forecast}


def matrix(actor) -> dict:
    """The department x category overview: assets by status group per cell (current, pipeline)."""
    available = set(settings_service.get("assets.available_statuses"))
    pipeline = set(settings_service.get("assets.pipeline_statuses"))
    query = (select(Asset.department_id, CapabilityModel.category_id, Asset.status_code, func.count())
             .join(CapabilityModel, CapabilityModel.id == Asset.model_id)
             .where(Asset.archived_at.is_(None))
             .group_by(Asset.department_id, CapabilityModel.category_id, Asset.status_code))
    scope = _scope_ids(actor)
    if scope is not None:
        query = query.where(Asset.department_id.in_(sorted(scope) or [-1]))
    cells: dict[tuple, dict] = defaultdict(lambda: {"current": 0, "pipeline": 0, "other": 0, "total": 0})
    for d, c, s, n in context.session().execute(query):
        cell = cells[(d, c)]
        cell["current" if s in available else "pipeline" if s in pipeline else "other"] += n
        cell["total"] += n
    departments = sorted((d for d in lk.by_id(Department).values() if d.archived_at is None),
                         key=lambda e: (e.sort_order, e.id))
    if scope is not None:
        departments = [d for d in departments if d.id in scope]
    categories = sorted((c for c in lk.by_id(CapabilityCategory).values() if c.archived_at is None),
                        key=lambda e: (e.sort_order, e.id))
    return {
        "departments": [lk.ref(d) for d in departments], "categories": [lk.ref(c) for c in categories],
        "cells": [{"departmentId": sid(d.id), "categoryId": sid(c.id), **cells[(d.id, c.id)],
                   "drill": {"department": [sid(d.id)], "category": [sid(c.id)]}}
                  for d in departments for c in categories],
    }
