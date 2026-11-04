"""Assets (each physical unit): registry list with filters, profile, create, update, archive.

The list query is also the drill-down: every dashboard figure about assets answers with the filters that reproduce
it here (metrics_service), so a number and the list behind it can never disagree."""
from __future__ import annotations

from datetime import date

from sqlalchemy import and_, extract, func, or_, select

from ..core.clock import iso_utc
from ..exceptions import ValidationFailed
from ..models import (Asset, AssetStatusHistory, CapabilityCategory, CapabilityModel, Contract, Department,
                      Organization, RequirementModel, CapabilityRequirement, Site)
from ..repositories import common as repo
from ..schemas.common import page_envelope
from ..schemas.dto import record_meta, sid
from ..security.auth import ALL_DEPARTMENTS, PERM_EDIT_ASSETS, department_scope
from . import crud, context, lookup_service as lk, settings_service

SORTS = {
    "code": Asset.code, "status": Asset.status_code, "department": Asset.department_id,
    "acquisition": Asset.acquisition_date, "readiness": Asset.readiness_operational, "model": Asset.model_id,
}
FILTERS = {"q", "department", "category", "model", "status", "site", "manufacturer", "acquisitionYear", "contract",
           "requirement", "readiness", "warranty", "statusGroup", "archived", "sort", "dir", "all"}
READINESS_BANDS = {"HIGH": (80, 100), "MEDIUM": (50, 79), "LOW": (0, 49)}


def overall_readiness(asset: Asset) -> int | None:
    """Weighted average of the readiness dimensions present (weights in Settings > Business rules)."""
    weights = settings_service.get("readiness.weights")
    parts = [(asset.readiness_operational, weights["operational"]), (asset.readiness_technical, weights["technical"]),
             (asset.readiness_mission, weights["mission"]), (asset.readiness_maintenance, weights["maintenance"])]
    present = [(v, w) for v, w in parts if v is not None and w > 0]
    if not present:
        return None
    total = sum(w for _, w in present)
    return round(sum(v * w for v, w in present) / total)


def age_years(asset: Asset, today: date) -> float | None:
    if asset.acquisition_date is None or asset.acquisition_date > today:
        return None
    return round((today - asset.acquisition_date).days / 365.25, 1)


def scope_filter(actor, column=Asset.department_id):
    scope = department_scope(actor)
    return None if scope is ALL_DEPARTMENTS else column.in_(sorted(scope) or [-1])


def status_group(name: str) -> list[str]:
    key = {"AVAILABLE": "assets.available_statuses", "OPERATIONAL": "assets.operational_statuses",
           "PIPELINE": "assets.pipeline_statuses"}.get(name)
    if key is None:
        raise ValidationFailed.field("statusGroup", "Must be AVAILABLE, OPERATIONAL or PIPELINE.")
    return list(settings_service.get(key))


def build_query(actor, f: dict):
    """f: parsed filters (see api/v1/assets.py). Returns a select of Asset with the joins the filters need."""
    query = select(Asset).join(CapabilityModel, CapabilityModel.id == Asset.model_id)
    conditions = []
    scope = scope_filter(actor)
    if scope is not None:
        conditions.append(scope)
    if not f.get("archived"):
        conditions.append(Asset.archived_at.is_(None))
    if f.get("q"):
        pattern = repo.like_pattern(f["q"])
        conditions.append(or_(func.lower(Asset.code).like(pattern, escape="\\"),
                              func.lower(Asset.serial_number).like(pattern, escape="\\"),
                              func.lower(CapabilityModel.name_en).like(pattern, escape="\\"),
                              func.lower(CapabilityModel.name_ar).like(pattern, escape="\\"),
                              func.lower(CapabilityModel.code).like(pattern, escape="\\")))
    if f.get("department"):
        conditions.append(Asset.department_id.in_(f["department"]))
    if f.get("category"):
        conditions.append(CapabilityModel.category_id.in_(f["category"]))
    if f.get("model"):
        conditions.append(Asset.model_id.in_(f["model"]))
    statuses = list(f.get("status") or [])
    if f.get("statusGroup"):
        group = status_group(f["statusGroup"])
        statuses = [s for s in statuses if s in group] if statuses else group
        if not statuses:
            statuses = ["-"]
    if statuses:
        conditions.append(Asset.status_code.in_(statuses))
    if f.get("site"):
        conditions.append(Asset.site_id.in_(f["site"]))
    if f.get("manufacturer"):
        conditions.append(CapabilityModel.manufacturer_id.in_(f["manufacturer"]))
    if f.get("contract"):
        conditions.append(Asset.contract_id.in_(f["contract"]))
    if f.get("acquisitionYear"):
        conditions.append(extract("year", Asset.acquisition_date) == f["acquisitionYear"])
    if f.get("requirement"):
        # Assets that count toward the requirement: its models, in its department.
        req_ids = f["requirement"]
        conditions.append(select(RequirementModel.requirement_id)
                          .join(CapabilityRequirement, CapabilityRequirement.id == RequirementModel.requirement_id)
                          .where(RequirementModel.requirement_id.in_(req_ids),
                                 RequirementModel.model_id == Asset.model_id,
                                 CapabilityRequirement.department_id == Asset.department_id).exists())
    if f.get("readiness"):
        low, high = READINESS_BANDS[f["readiness"]]
        conditions.append(and_(Asset.readiness_operational >= low, Asset.readiness_operational <= high))
    if f.get("warranty"):
        today = context.today()
        if f["warranty"] == "ACTIVE":
            conditions.append(Asset.warranty_end_date >= today)
        else:
            conditions.append(or_(Asset.warranty_end_date < today, Asset.warranty_end_date.is_(None)))
    if conditions:
        query = query.where(*conditions)
    return query


def list_assets(actor, f: dict, page: int, size: int) -> dict:
    session = context.session()
    query = build_query(actor, f)
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    column = SORTS.get(f.get("sort") or "code", Asset.code)
    order = column.desc() if f.get("dir") == "desc" else column.asc()
    if f.get("all"):
        page, size = 0, 5000
    rows = session.scalars(query.order_by(order, Asset.id).offset(page * size).limit(size)).all()
    return page_envelope([asset_dto(a) for a in rows], page, size, total)


def count_assets(actor, f: dict) -> int:
    return context.session().scalar(select(func.count()).select_from(build_query(actor, f).subquery()))


def asset_dto(a: Asset, full: bool = False) -> dict:
    models = lk.by_id(CapabilityModel)
    model = models.get(a.model_id)
    status = lk.statuses("ASSET").get(a.status_code)
    category = lk.by_id(CapabilityCategory).get(model.category_id) if model else None
    manufacturer = lk.by_id(Organization).get(model.manufacturer_id) if model and model.manufacturer_id else None
    today = context.today()
    out = {
        "id": sid(a.id), "code": a.code, "serialNumber": a.serial_number,
        "model": lk.ref(model), "category": lk.ref(category),
        "department": lk.ref_id(Department, a.department_id), "site": lk.ref_id(Site, a.site_id),
        "manufacturer": lk.ref(manufacturer),
        "status": a.status_code,
        "statusColor": status.color if status else "grey",
        "readiness": {"operational": a.readiness_operational, "technical": a.readiness_technical,
                      "mission": a.readiness_mission, "maintenance": a.readiness_maintenance,
                      "overall": overall_readiness(a)},
        "acquisitionDate": a.acquisition_date.isoformat() if a.acquisition_date else None,
        "expectedDeliveryDate": a.expected_delivery_date.isoformat() if a.expected_delivery_date else None,
        "warrantyEndDate": a.warranty_end_date.isoformat() if a.warranty_end_date else None,
        "ageYears": age_years(a, today),
        **record_meta(a),
    }
    if full:
        contract = context.session().get(Contract, a.contract_id) if a.contract_id else None
        out.update({
            "acquisitionMethod": a.acquisition_method,
            "contract": {"id": sid(contract.id), "code": contract.code, "titleEn": contract.title_en,
                         "titleAr": contract.title_ar,
                         "supplier": lk.ref_id(Organization, contract.supplier_id)} if contract else None,
            "unitValue": a.unit_value, "serviceLifeYears": a.service_life_years, "operatingHours": a.operating_hours,
            "responsibleEn": a.responsible_en, "responsibleAr": a.responsible_ar, "notes": a.notes,
            "warrantyActive": bool(a.warranty_end_date and a.warranty_end_date >= today),
        })
    return out


def get_asset(actor, asset_id: int) -> dict:
    asset = crud.load(Asset, asset_id, actor, "Asset")
    out = asset_dto(asset, full=True)
    rows = context.session().scalars(select(AssetStatusHistory).where(AssetStatusHistory.asset_id == asset.id)
                                     .order_by(AssetStatusHistory.changed_at.desc(), AssetStatusHistory.id.desc()))
    out["statusHistory"] = [{"status": h.status_code, "readiness": h.readiness, "changedAt": iso_utc(h.changed_at),
                             "note": h.note} for h in rows]
    return out


_FIELDS = ("serial_number", "model_id", "department_id", "site_id", "status_code", "readiness_operational",
           "readiness_technical", "readiness_mission", "readiness_maintenance", "acquisition_date",
           "expected_delivery_date", "acquisition_method", "contract_id", "warranty_end_date", "unit_value",
           "service_life_years", "operating_hours", "responsible_en", "responsible_ar", "notes")


def _validate(values: dict, current: Asset | None = None) -> None:
    if "model_id" in values:
        crud.check_ref(CapabilityModel, values["model_id"], "modelId", "Model",
                       allow_archived=current is not None and current.model_id == values["model_id"])
    if "department_id" in values:
        crud.check_ref(Department, values["department_id"], "departmentId", "Department",
                       allow_archived=current is not None and current.department_id == values["department_id"])
    if values.get("site_id") is not None:
        crud.check_ref(Site, values["site_id"], "siteId", "Site",
                       allow_archived=current is not None and current.site_id == values["site_id"])
    if values.get("contract_id") is not None:
        crud.check_ref(Contract, values["contract_id"], "contractId", "Contract", allow_archived=True)
    if "status_code" in values:
        crud.check_status("ASSET", values["status_code"], "status", current.status_code if current else None)
    serial = values.get("serial_number")
    if serial:
        query = select(Asset.id).where(func.upper(Asset.serial_number) == serial.upper())
        if current is not None:
            query = query.where(Asset.id != current.id)
        if context.session().scalar(query) is not None:
            from ..exceptions import Duplicate
            raise Duplicate.field("serialNumber", f"Serial number {serial} is already used.")


def _history(actor, asset: Asset, note: str | None = None) -> None:
    context.session().add(AssetStatusHistory(asset_id=asset.id, status_code=asset.status_code,
                                             readiness=overall_readiness(asset), changed_at=context.now(),
                                             changed_by=actor.id, note=note))


def create_asset(actor, data) -> dict:
    values = {k: getattr(data, k) for k in _FIELDS}
    crud.check_unique_code(Asset, data.code)
    _validate(values)
    asset = Asset(code=data.code, **values)
    crud.create(actor, asset, PERM_EDIT_ASSETS, data.department_id, commit=False)
    _history(actor, asset, "Created")
    context.session().commit()
    return get_asset(actor, asset.id)


def update_asset(actor, asset_id: int, data) -> dict:
    asset = crud.load(Asset, asset_id, actor, "Asset", for_update=True)
    changes = {k: v for k, v in data.changes().items() if k in _FIELDS}
    _validate(changes, asset)
    tracked = (asset.status_code, overall_readiness(asset))
    changed = crud.update(actor, asset, changes, PERM_EDIT_ASSETS, data.version, data.reason,
                          department_ids=(asset.department_id, changes.get("department_id", asset.department_id)),
                          commit=False)
    if changed and (asset.status_code, overall_readiness(asset)) != tracked:
        _history(actor, asset, data.reason)
    context.session().commit()
    return get_asset(actor, asset.id)


def archive_asset(actor, asset_id: int, archived: bool, version: int | None, reason: str | None) -> dict:
    asset = crud.load(Asset, asset_id, actor, "Asset", for_update=True)
    crud.set_archived(actor, asset, archived, PERM_EDIT_ASSETS, version, reason)
    return get_asset(actor, asset.id)
