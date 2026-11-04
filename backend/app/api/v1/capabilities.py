"""Lookups, assets, models, requirements, completion, gaps and the department x category matrix."""
from __future__ import annotations

import csv
import io

from flask import Response, jsonify, request

from ...exceptions import ValidationFailed
from ...schemas.capability import (ArchiveRequest, AssetCreate, AssetUpdate, ModelCreate, ModelUpdate,
                                   RequirementCreate, RequirementUpdate)
from ...schemas.common import Query, parse_id
from ...security.auth import PERM_EXPORT, PERM_VIEW, permission_required, require_permission
from ...services import asset_service, capability_service, lookup_service, metrics_service, search_service
from . import body, bp, created, user


def id_list(query: Query, name: str) -> list[int]:
    raw = (query.args.get(name) or "").strip()
    if not raw:
        return []
    try:
        return [parse_id(part) for part in raw.split(",") if part.strip()]
    except ValueError:
        raise ValidationFailed.field(name, "Must be a list of ids.") from None


def _codes(query: Query, name: str) -> list[str]:
    raw = (query.args.get(name) or "").strip().upper()
    return [c.strip() for c in raw.split(",") if c.strip()]


@bp.get("/lookups")
@permission_required(PERM_VIEW)
def lookups():
    Query(request.args, set())
    return jsonify(lookup_service.lookups())


# ---------------------------------------------------------------- assets -------------------------------------------


def asset_filters(query: Query) -> dict:
    year = query.text("acquisitionYear", 4)
    if year is not None and not year.isdigit():
        raise ValidationFailed.field("acquisitionYear", "Must be a year.")
    return {
        "q": query.text("q", 100),
        "department": id_list(query, "department"), "category": id_list(query, "category"),
        "model": id_list(query, "model"), "site": id_list(query, "site"),
        "manufacturer": id_list(query, "manufacturer"), "contract": id_list(query, "contract"),
        "requirement": id_list(query, "requirement"),
        "status": _codes(query, "status"),
        "statusGroup": query.choice("statusGroup", ("AVAILABLE", "OPERATIONAL", "PIPELINE")),
        "acquisitionYear": int(year) if year else None,
        "readiness": query.choice("readiness", tuple(asset_service.READINESS_BANDS)),
        "warranty": query.choice("warranty", ("ACTIVE", "EXPIRED")),
        "archived": query.boolean("archived"),
        "sort": query.choice("sort", tuple(s.upper() for s in asset_service.SORTS)),
        "dir": (query.choice("dir", ("ASC", "DESC")) or "ASC").lower(),
        "all": query.boolean("all"),
    }


@bp.get("/assets")
@permission_required(PERM_VIEW)
def list_assets():
    query = Query(request.args, asset_service.FILTERS)
    page, size = query.page()
    f = asset_filters(query)
    if f["sort"]:
        f["sort"] = f["sort"].lower()
    return jsonify(asset_service.list_assets(user(), f, page, size))


_CSV_COLUMNS = (("code", "Asset ID"), ("serialNumber", "Serial number"), ("model", "Model"),
                ("category", "Category"), ("department", "Department"), ("site", "Site"), ("status", "Status"),
                ("operational", "Operational readiness %"), ("overall", "Overall readiness %"),
                ("acquisitionDate", "Acquisition date"), ("expectedDeliveryDate", "Expected delivery"),
                ("manufacturer", "Manufacturer"))


def csv_response(rows: list[list], filename: str) -> Response:
    out = io.StringIO()
    writer = csv.writer(out)
    for row in rows:
        # A cell starting with = + - @ would run as a formula in Excel: prefix it (CSV injection).
        writer.writerow([("'" + v) if isinstance(v, str) and v[:1] in ("=", "+", "-", "@") else v for v in row])
    response = Response("﻿" + out.getvalue(), mimetype="text/csv")
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@bp.get("/assets.csv")
@permission_required(PERM_VIEW)
def export_assets():
    require_permission(user(), PERM_EXPORT)
    query = Query(request.args, asset_service.FILTERS | {"lang"})
    f = asset_filters(query)
    f["all"] = True
    if f["sort"]:
        f["sort"] = f["sort"].lower()
    arabic = query.choice("lang", ("EN", "AR")) == "AR"
    name = "nameAr" if arabic else "nameEn"
    statuses = lookup_service.statuses("ASSET")
    rows = [[label for _, label in _CSV_COLUMNS]]
    for a in asset_service.list_assets(user(), f, 0, 5000)["items"]:
        status = statuses.get(a["status"])
        rows.append([a["code"], a["serialNumber"], (a["model"] or {}).get(name), (a["category"] or {}).get("code"),
                     (a["department"] or {}).get(name), (a["site"] or {}).get(name),
                     (status.name_ar if arabic else status.name_en) if status else a["status"],
                     a["readiness"]["operational"], a["readiness"]["overall"], a["acquisitionDate"],
                     a["expectedDeliveryDate"], (a["manufacturer"] or {}).get(name)])
    return csv_response(rows, "assets.csv")


@bp.get("/assets/<int:asset_id>")
@permission_required(PERM_VIEW)
def get_asset(asset_id: int):
    Query(request.args, set())
    return jsonify(asset_service.get_asset(user(), asset_id))


@bp.post("/assets")
def create_asset():
    data = AssetCreate.model_validate(body())
    result = asset_service.create_asset(user(), data)
    return created(result, f"/api/v1/assets/{result['id']}")


@bp.patch("/assets/<int:asset_id>")
def update_asset(asset_id: int):
    return jsonify(asset_service.update_asset(user(), asset_id, AssetUpdate.model_validate(body())))


@bp.post("/assets/<int:asset_id>/archive")
def archive_asset(asset_id: int):
    data = ArchiveRequest.model_validate(body())
    return jsonify(asset_service.archive_asset(user(), asset_id, data.archived, data.version, data.reason))


# ---------------------------------------------------------------- models -------------------------------------------


@bp.get("/models")
@permission_required(PERM_VIEW)
def list_models():
    query = Query(request.args, {"category", "q", "archived"})
    return jsonify({"items": capability_service.list_models(user(), query.id("category"), query.text("q", 100),
                                                            bool(query.boolean("archived")))})


@bp.get("/models/<int:model_id>")
@permission_required(PERM_VIEW)
def get_model(model_id: int):
    Query(request.args, set())
    return jsonify(capability_service.get_model(user(), model_id))


@bp.post("/models")
def create_model():
    result = capability_service.create_model(user(), ModelCreate.model_validate(body()))
    return created(result, f"/api/v1/models/{result['id']}")


@bp.patch("/models/<int:model_id>")
def update_model(model_id: int):
    return jsonify(capability_service.update_model(user(), model_id, ModelUpdate.model_validate(body())))


@bp.post("/models/<int:model_id>/archive")
def archive_model(model_id: int):
    data = ArchiveRequest.model_validate(body())
    return jsonify(capability_service.archive_model(user(), model_id, data.archived, data.version, data.reason))


# ---------------------------------------------------------------- requirements -------------------------------------


@bp.get("/requirements")
@permission_required(PERM_VIEW)
def list_requirements():
    query = Query(request.args, {"department", "category"})
    return jsonify({"items": capability_service.list_requirements(user(), query.id("department"),
                                                                  query.id("category"))})


@bp.get("/requirements/<int:requirement_id>")
@permission_required(PERM_VIEW)
def get_requirement(requirement_id: int):
    Query(request.args, set())
    return jsonify(capability_service.get_requirement(user(), requirement_id))


@bp.post("/requirements")
def create_requirement():
    result = capability_service.create_requirement(user(), RequirementCreate.model_validate(body()))
    return created(result, f"/api/v1/requirements/{result['id']}")


@bp.patch("/requirements/<int:requirement_id>")
def update_requirement(requirement_id: int):
    return jsonify(capability_service.update_requirement(user(), requirement_id,
                                                         RequirementUpdate.model_validate(body())))


@bp.post("/requirements/<int:requirement_id>/archive")
def archive_requirement(requirement_id: int):
    data = ArchiveRequest.model_validate(body())
    return jsonify(capability_service.archive_requirement(user(), requirement_id, data.archived, data.version,
                                                          data.reason))


# ---------------------------------------------------------------- analysis -----------------------------------------


@bp.get("/completion")
@permission_required(PERM_VIEW)
def completion():
    query = Query(request.args, {"by"})
    by = (query.choice("by", ("DEPARTMENT", "CATEGORY")) or "DEPARTMENT").lower()
    return jsonify(metrics_service.completion(user(), by))


@bp.get("/gaps")
@permission_required(PERM_VIEW)
def gaps():
    query = Query(request.args, {"forecast"})
    forecast = bool(query.boolean("forecast"))
    result = metrics_service.gap_heatmap(user(), forecast)
    result["byDepartment"] = metrics_service.completion(user(), "department")["groups"]
    result["byCategory"] = metrics_service.completion(user(), "category")["groups"]
    rows = metrics_service.requirement_metrics(user())
    order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    result["register"] = sorted((r for r in rows if r["gap"] > 0),
                                key=lambda r: (not r["critical"], order[r["priority"]], -r["forecastGap"], r["code"]))
    return jsonify(result)


@bp.get("/matrix")
@permission_required(PERM_VIEW)
def matrix():
    Query(request.args, set())
    return jsonify(metrics_service.matrix(user()))


@bp.get("/search")
@permission_required(PERM_VIEW)
def search():
    query = Query(request.args, {"q"})
    q = query.text("q", 100)
    if not q:
        raise ValidationFailed.field("q", "Type something to search for.")
    return jsonify(search_service.search(user(), q))
