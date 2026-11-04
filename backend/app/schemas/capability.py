"""Request bodies for requirements, models and assets."""
from __future__ import annotations

from typing import Annotated, Any, ClassVar, Literal

from pydantic import AfterValidator, BeforeValidator

from ..models.capability import ACQUISITION_METHODS, PRIORITIES
from .common import (Amount, ApiModel, Count, DateOnly, Id, PatchModel, Percent, Quantity, Reason, Version, code_text,
                     optional_text, required_text)


def _upper(value):
    return value.strip().upper() if isinstance(value, str) else value


def _upper_or_none(value):
    if isinstance(value, str):
        value = value.strip().upper()
        return value or None
    return value


Name = required_text(1, 200)
Priority = Annotated[Literal[PRIORITIES], BeforeValidator(_upper)]  # type: ignore[valid-type]
def _status(value: str) -> str:
    if not (2 <= len(value) <= 30) or not value.replace("_", "").isalnum() or not value.isascii():
        raise ValueError("Not a status code.")
    return value


StatusCode = Annotated[str, BeforeValidator(_upper), AfterValidator(_status)]
AcquisitionMethod = Annotated[Literal[ACQUISITION_METHODS] | None, BeforeValidator(_upper_or_none)]  # type: ignore[valid-type]


class ArchiveRequest(ApiModel):
    archived: bool
    version: Version | None = None
    reason: Reason = None


class RequirementCreate(ApiModel):
    code: code_text(2, 20)
    name_en: Name
    name_ar: Name
    department_id: Id
    category_id: Id
    required_qty: Quantity
    priority: Priority
    target_date: DateOnly = None
    notes: optional_text(4000) = None
    model_ids: list[Id] = []


class RequirementUpdate(PatchModel):
    REQUIRED_ON_PATCH: ClassVar[tuple[str, ...]] = ("name_en", "name_ar", "department_id", "category_id",
                                                    "required_qty", "priority")
    name_en: Name | None = None
    name_ar: Name | None = None
    department_id: Id | None = None
    category_id: Id | None = None
    required_qty: Quantity | None = None
    priority: Priority | None = None
    target_date: DateOnly = None
    notes: optional_text(4000) = None
    model_ids: list[Id] | None = None
    reason: Reason = None
    version: Version | None = None

    def changes(self) -> dict[str, Any]:
        out = super().changes()
        out.pop("model_ids", None)
        return out


class ModelCreate(ApiModel):
    code: code_text(2, 20)
    name_en: required_text(1, 160)
    name_ar: required_text(1, 160)
    category_id: Id
    manufacturer_id: Id | None = None
    role_en: optional_text(200) = None
    role_ar: optional_text(200) = None
    unit_cost: Amount = None
    specs: dict[str, Any] | None = None
    notes: optional_text(4000) = None


class ModelUpdate(PatchModel):
    REQUIRED_ON_PATCH: ClassVar[tuple[str, ...]] = ("name_en", "name_ar", "category_id")
    name_en: required_text(1, 160) | None = None
    name_ar: required_text(1, 160) | None = None
    category_id: Id | None = None
    manufacturer_id: Id | None = None
    role_en: optional_text(200) = None
    role_ar: optional_text(200) = None
    unit_cost: Amount = None
    specs: dict[str, Any] | None = None
    notes: optional_text(4000) = None
    reason: Reason = None
    version: Version | None = None

    def changes(self) -> dict[str, Any]:
        out = super().changes()
        out.pop("specs", None)
        return out


class _AssetFields(ApiModel):
    serial_number: optional_text(60) = None
    site_id: Id | None = None
    readiness_operational: Percent = None
    readiness_technical: Percent = None
    readiness_mission: Percent = None
    readiness_maintenance: Percent = None
    acquisition_date: DateOnly = None
    expected_delivery_date: DateOnly = None
    acquisition_method: AcquisitionMethod = None
    contract_id: Id | None = None
    warranty_end_date: DateOnly = None
    unit_value: Amount = None
    service_life_years: Count = None
    operating_hours: Count = None
    responsible_en: optional_text(160) = None
    responsible_ar: optional_text(160) = None
    notes: optional_text(4000) = None


class AssetCreate(_AssetFields):
    code: code_text(2, 30)
    model_id: Id
    department_id: Id
    status_code: StatusCode


class AssetUpdate(_AssetFields, PatchModel):
    REQUIRED_ON_PATCH: ClassVar[tuple[str, ...]] = ("model_id", "department_id", "status_code")
    model_id: Id | None = None
    department_id: Id | None = None
    status_code: StatusCode | None = None
    reason: Reason = None
    version: Version | None = None
