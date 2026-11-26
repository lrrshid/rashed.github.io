"""Testing & evaluation, maintenance orders, AI technologies and levels, development opportunities."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import UTCDateTime
from .base import ArchivableMixin, AuditedMixin, Base, IdType, Money, NamedMixin, code_column, id_column

TEST_TYPES = ("INTERNAL", "EXTERNAL")
MAINT_TYPES = ("PREVENTIVE", "CORRECTIVE", "INSPECTION", "UPGRADE")
DEV_TYPES = ("AI", "SENSORS", "ENDURANCE", "COMMUNICATIONS", "AUTONOMY", "PAYLOAD", "SECURITY", "INTEGRATION", "OTHER")
COMPLEXITIES = ("LOW", "MEDIUM", "HIGH")


class TestEvent(AuditedMixin, ArchivableMixin, Base):
    __tablename__ = "test_event"
    __test__ = False  # not a pytest class

    id: Mapped[int] = id_column("test_event_seq")
    code: Mapped[str] = code_column()
    title_en: Mapped[str] = mapped_column(String(200), nullable=False)
    title_ar: Mapped[str] = mapped_column(String(200), nullable=False)
    model_id: Mapped[int] = mapped_column(IdType, ForeignKey("capability_model.id"), nullable=False)
    asset_id: Mapped[int | None] = mapped_column(IdType, ForeignKey("asset.id"))
    project_id: Mapped[int | None] = mapped_column(IdType, ForeignKey("project.id"))
    department_id: Mapped[int] = mapped_column(IdType, ForeignKey("department.id"), nullable=False)
    site_id: Mapped[int | None] = mapped_column(IdType, ForeignKey("site.id"))
    unit_id: Mapped[int | None] = mapped_column(IdType, ForeignKey("org_unit.id"))  # the conducting section
    test_type: Mapped[str] = mapped_column(String(10), nullable=False)
    test_date: Mapped[date] = mapped_column(Date, nullable=False)
    status_code: Mapped[str] = mapped_column(String(30), nullable=False)
    score: Mapped[int | None] = mapped_column(Integer)
    result_en: Mapped[str | None] = mapped_column(Text)
    result_ar: Mapped[str | None] = mapped_column(Text)


class MaintenanceOrder(AuditedMixin, ArchivableMixin, Base):
    __tablename__ = "maintenance_order"

    id: Mapped[int] = id_column("maintenance_order_seq")
    code: Mapped[str] = code_column()
    asset_id: Mapped[int] = mapped_column(IdType, ForeignKey("asset.id"), nullable=False)
    maint_type: Mapped[str] = mapped_column(String(12), nullable=False)
    title_en: Mapped[str] = mapped_column(String(200), nullable=False)
    title_ar: Mapped[str] = mapped_column(String(200), nullable=False)
    status_code: Mapped[str] = mapped_column(String(30), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    expected_end_date: Mapped[date | None] = mapped_column(Date)
    actual_end_date: Mapped[date | None] = mapped_column(Date)
    progress_pct: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost: Mapped[float | None] = mapped_column(Money)
    parts_shortage: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    parts_text: Mapped[str | None] = mapped_column(String(500))
    performed_by: Mapped[str | None] = mapped_column(String(160))
    # Why the capability entered maintenance (Maintenance > Capability maintenance); the investigation board's scan is
    # an attached document of type INVESTIGATION.
    entry_reason_en: Mapped[str | None] = mapped_column(Text)
    entry_reason_ar: Mapped[str | None] = mapped_column(Text)


class GoldenSampleTrial(AuditedMixin, ArchivableMixin, Base):
    """A trial of a golden sample (the reference unit of a capability model). Its trial record, the higher-level
    directive letter and the official trial form are attached documents (GOLDEN_TRIAL, DIRECTIVE_LETTER,
    OFFICIAL_TRIAL_FORM). Status: the TEST status list."""
    __tablename__ = "golden_sample_trial"

    id: Mapped[int] = id_column("golden_sample_trial_seq")
    code: Mapped[str] = code_column()
    title_en: Mapped[str] = mapped_column(String(200), nullable=False)
    title_ar: Mapped[str] = mapped_column(String(200), nullable=False)
    model_id: Mapped[int] = mapped_column(IdType, ForeignKey("capability_model.id"), nullable=False)
    trial_date: Mapped[date] = mapped_column(Date, nullable=False)
    status_code: Mapped[str] = mapped_column(String(30), nullable=False)
    notes_en: Mapped[str | None] = mapped_column(Text)
    notes_ar: Mapped[str | None] = mapped_column(Text)


class AiTechnology(NamedMixin, AuditedMixin, ArchivableMixin, Base):
    __tablename__ = "ai_technology"

    id: Mapped[int] = id_column("ai_technology_seq")
    code: Mapped[str] = code_column(30)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class ModelAiTech(Base):
    __tablename__ = "model_ai_tech"

    model_id: Mapped[int] = mapped_column(IdType, ForeignKey("capability_model.id"), primary_key=True)
    technology_id: Mapped[int] = mapped_column(IdType, ForeignKey("ai_technology.id"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)


class AiLevelCriterion(NamedMixin, AuditedMixin, Base):
    __tablename__ = "ai_level_criterion"

    id: Mapped[int] = id_column("ai_level_criterion_seq")
    ai_level: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    description_en: Mapped[str | None] = mapped_column(String(500))
    description_ar: Mapped[str | None] = mapped_column(String(500))
    min_supported: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    required_codes: Mapped[str | None] = mapped_column(String(500))

    @property
    def required(self) -> list[str]:
        return [c.strip() for c in (self.required_codes or "").split(",") if c.strip()]


class DevelopmentOpportunity(AuditedMixin, ArchivableMixin, Base):
    __tablename__ = "development_opportunity"

    id: Mapped[int] = id_column("development_opportunity_seq")
    code: Mapped[str] = code_column()
    model_id: Mapped[int] = mapped_column(IdType, ForeignKey("capability_model.id"), nullable=False)
    dev_type: Mapped[str] = mapped_column(String(20), nullable=False)
    title_en: Mapped[str] = mapped_column(String(200), nullable=False)
    title_ar: Mapped[str] = mapped_column(String(200), nullable=False)
    benefit_en: Mapped[str | None] = mapped_column(String(500))
    benefit_ar: Mapped[str | None] = mapped_column(String(500))
    status_code: Mapped[str] = mapped_column(String(30), nullable=False)
    complexity: Mapped[str] = mapped_column(String(10), nullable=False)
    estimated_cost: Mapped[float | None] = mapped_column(Money)
    duration_months: Mapped[int | None] = mapped_column(Integer)
    priority: Mapped[str] = mapped_column(String(10), nullable=False)
    project_id: Mapped[int | None] = mapped_column(IdType, ForeignKey("project.id"))
