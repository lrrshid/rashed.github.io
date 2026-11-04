"""The capability records: requirement -> model -> asset, plus contracts and the asset status history.
Linked, never merged: completion, gaps and readiness are computed from them (services/metrics_service.py)."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.database import UTCDateTime
from .base import ArchivableMixin, AuditedMixin, Base, IdType, Money, NamedMixin, code_column, id_column, user_fk

PRIORITIES = ("CRITICAL", "HIGH", "MEDIUM", "LOW")
ACQUISITION_METHODS = ("DIRECT_CONTRACT", "TENDER", "GOVERNMENT", "DONATION", "DEVELOPMENT", "OTHER")


class RequirementModel(Base):
    __tablename__ = "requirement_model"

    requirement_id: Mapped[int] = mapped_column(IdType, ForeignKey("capability_requirement.id"), primary_key=True)
    model_id: Mapped[int] = mapped_column(IdType, ForeignKey("capability_model.id"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)


class CapabilityRequirement(NamedMixin, AuditedMixin, ArchivableMixin, Base):
    """What is operationally required: a quantity of a category in a department."""

    __tablename__ = "capability_requirement"

    id: Mapped[int] = id_column("capability_requirement_seq")
    code: Mapped[str] = code_column()
    department_id: Mapped[int] = mapped_column(IdType, ForeignKey("department.id"), nullable=False)
    category_id: Mapped[int] = mapped_column(IdType, ForeignKey("capability_category.id"), nullable=False)
    required_qty: Mapped[int] = mapped_column(Integer, nullable=False)
    priority: Mapped[str] = mapped_column(String(10), nullable=False)
    target_date: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)

    model_links: Mapped[list[RequirementModel]] = relationship(
        RequirementModel, cascade="all, delete-orphan", order_by=RequirementModel.model_id)

    @property
    def model_ids(self) -> list[int]:
        return [link.model_id for link in self.model_links]


class CapabilityModel(NamedMixin, AuditedMixin, ArchivableMixin, Base):
    """The platform or system."""

    __tablename__ = "capability_model"

    id: Mapped[int] = id_column("capability_model_seq")
    code: Mapped[str] = code_column()
    category_id: Mapped[int] = mapped_column(IdType, ForeignKey("capability_category.id"), nullable=False)
    manufacturer_id: Mapped[int | None] = mapped_column(IdType, ForeignKey("organization.id"))
    role_en: Mapped[str | None] = mapped_column(String(200))
    role_ar: Mapped[str | None] = mapped_column(String(200))
    unit_cost: Mapped[float | None] = mapped_column(Money)
    specs_json: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)


class Contract(AuditedMixin, ArchivableMixin, Base):
    __tablename__ = "contract"

    id: Mapped[int] = id_column("contract_seq")
    code: Mapped[str] = code_column(30)
    title_en: Mapped[str] = mapped_column(String(200), nullable=False)
    title_ar: Mapped[str] = mapped_column(String(200), nullable=False)
    supplier_id: Mapped[int | None] = mapped_column(IdType, ForeignKey("organization.id"))
    contract_value: Mapped[float | None] = mapped_column(Money)
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)


class Asset(AuditedMixin, ArchivableMixin, Base):
    """Each physical unit."""

    __tablename__ = "asset"

    id: Mapped[int] = id_column("asset_seq")
    code: Mapped[str] = code_column(30)
    serial_number: Mapped[str | None] = mapped_column(String(60))
    model_id: Mapped[int] = mapped_column(IdType, ForeignKey("capability_model.id"), nullable=False)
    department_id: Mapped[int] = mapped_column(IdType, ForeignKey("department.id"), nullable=False)
    site_id: Mapped[int | None] = mapped_column(IdType, ForeignKey("site.id"))
    status_code: Mapped[str] = mapped_column(String(30), nullable=False)
    readiness_operational: Mapped[int | None] = mapped_column(Integer)
    readiness_technical: Mapped[int | None] = mapped_column(Integer)
    readiness_mission: Mapped[int | None] = mapped_column(Integer)
    readiness_maintenance: Mapped[int | None] = mapped_column(Integer)
    acquisition_date: Mapped[date | None] = mapped_column(Date)
    expected_delivery_date: Mapped[date | None] = mapped_column(Date)
    acquisition_method: Mapped[str | None] = mapped_column(String(20))
    contract_id: Mapped[int | None] = mapped_column(IdType, ForeignKey("contract.id"))
    warranty_end_date: Mapped[date | None] = mapped_column(Date)
    unit_value: Mapped[float | None] = mapped_column(Money)
    service_life_years: Mapped[int | None] = mapped_column(Integer)
    operating_hours: Mapped[int | None] = mapped_column(Integer)
    responsible_en: Mapped[str | None] = mapped_column(String(160))
    responsible_ar: Mapped[str | None] = mapped_column(String(160))
    notes: Mapped[str | None] = mapped_column(Text)


class AssetStatusHistory(Base):
    __tablename__ = "asset_status_history"

    id: Mapped[int] = id_column("asset_status_history_seq")
    asset_id: Mapped[int] = mapped_column(IdType, ForeignKey("asset.id"), nullable=False)
    status_code: Mapped[str] = mapped_column(String(30), nullable=False)
    readiness: Mapped[int | None] = mapped_column(Integer)
    changed_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    changed_by: Mapped[int] = user_fk()
    note: Mapped[str | None] = mapped_column(Text)


class MetricSnapshot(Base):
    __tablename__ = "metric_snapshot"

    id: Mapped[int] = id_column("metric_snapshot_seq")
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    metric: Mapped[str] = mapped_column(String(60), nullable=False)
    department_id: Mapped[int | None] = mapped_column(IdType, ForeignKey("department.id"))
    category_id: Mapped[int | None] = mapped_column(IdType, ForeignKey("capability_category.id"))
    value: Mapped[float] = mapped_column(Money, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
