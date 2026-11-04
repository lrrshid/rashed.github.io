"""Projects (acquisition, development, upgrade, replacement, trials, research) and their milestones, risks, issues."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.database import UTCDateTime
from .base import ArchivableMixin, AuditedMixin, Base, IdType, Money, NamedMixin, code_column, id_column

MODEL_RELATIONS = ("CREATE", "UPGRADE", "REPLACE")
HEALTH_NOTE_DIMENSIONS = ("SCOPE", "PROCUREMENT")
RAGS = ("GREEN", "AMBER", "RED")
RISK_CATEGORIES = ("TECHNICAL", "SCHEDULE", "FINANCIAL", "SUPPLY_CHAIN", "COMMERCIAL", "OPERATIONAL", "ENVIRONMENTAL",
                   "REGULATORY")
SEVERITIES = ("CRITICAL", "HIGH", "MEDIUM", "LOW")


class ProjectRequirement(Base):
    __tablename__ = "project_requirement"

    project_id: Mapped[int] = mapped_column(IdType, ForeignKey("project.id"), primary_key=True)
    requirement_id: Mapped[int] = mapped_column(IdType, ForeignKey("capability_requirement.id"), primary_key=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)


class ProjectModel(Base):
    __tablename__ = "project_model"

    project_id: Mapped[int] = mapped_column(IdType, ForeignKey("project.id"), primary_key=True)
    model_id: Mapped[int] = mapped_column(IdType, ForeignKey("capability_model.id"), primary_key=True)
    relation: Mapped[str] = mapped_column(String(10), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)


class Project(NamedMixin, AuditedMixin, ArchivableMixin, Base):
    __tablename__ = "project"

    id: Mapped[int] = id_column("project_seq")
    code: Mapped[str] = code_column()
    project_type_id: Mapped[int] = mapped_column(IdType, ForeignKey("project_type.id"), nullable=False)
    department_id: Mapped[int] = mapped_column(IdType, ForeignKey("department.id"), nullable=False)
    category_id: Mapped[int] = mapped_column(IdType, ForeignKey("capability_category.id"), nullable=False)
    status_code: Mapped[str] = mapped_column(String(30), nullable=False)
    stage_id: Mapped[int | None] = mapped_column(IdType, ForeignKey("workflow_stage.id"))
    manager_name: Mapped[str | None] = mapped_column(String(160))
    supplier_id: Mapped[int | None] = mapped_column(IdType, ForeignKey("organization.id"))
    contract_id: Mapped[int | None] = mapped_column(IdType, ForeignKey("contract.id"))
    budget: Mapped[float | None] = mapped_column(Money)
    committed: Mapped[float | None] = mapped_column(Money)
    actual_spend: Mapped[float | None] = mapped_column(Money)
    progress_pct: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    start_date: Mapped[date | None] = mapped_column(Date)
    baseline_end_date: Mapped[date | None] = mapped_column(Date)
    target_end_date: Mapped[date | None] = mapped_column(Date)
    forecast_end_date: Mapped[date | None] = mapped_column(Date)
    actual_end_date: Mapped[date | None] = mapped_column(Date)
    next_action_en: Mapped[str | None] = mapped_column(Text)
    next_action_ar: Mapped[str | None] = mapped_column(Text)
    notes_en: Mapped[str | None] = mapped_column(Text)
    notes_ar: Mapped[str | None] = mapped_column(Text)

    requirement_links: Mapped[list[ProjectRequirement]] = relationship(
        ProjectRequirement, cascade="all, delete-orphan", order_by=ProjectRequirement.requirement_id)
    model_links: Mapped[list[ProjectModel]] = relationship(
        ProjectModel, cascade="all, delete-orphan", order_by=ProjectModel.model_id)


class ProjectHealthNote(AuditedMixin, Base):
    __tablename__ = "project_health_note"

    id: Mapped[int] = id_column("project_health_note_seq")
    project_id: Mapped[int] = mapped_column(IdType, ForeignKey("project.id"), nullable=False)
    dimension: Mapped[str] = mapped_column(String(20), nullable=False)
    rag: Mapped[str] = mapped_column(String(10), nullable=False)
    reason_en: Mapped[str | None] = mapped_column(Text)
    reason_ar: Mapped[str | None] = mapped_column(Text)


class Milestone(NamedMixin, AuditedMixin, ArchivableMixin, Base):
    __tablename__ = "milestone"

    id: Mapped[int] = id_column("milestone_seq")
    project_id: Mapped[int] = mapped_column(IdType, ForeignKey("project.id"), nullable=False)
    stage_id: Mapped[int | None] = mapped_column(IdType, ForeignKey("workflow_stage.id"))
    owner_name: Mapped[str | None] = mapped_column(String(160))
    planned_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    planned_end_date: Mapped[date] = mapped_column(Date, nullable=False)
    actual_end_date: Mapped[date | None] = mapped_column(Date)
    forecast_end_date: Mapped[date | None] = mapped_column(Date)
    status_code: Mapped[str] = mapped_column(String(30), nullable=False)
    progress_pct: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_major: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class Risk(AuditedMixin, ArchivableMixin, Base):
    __tablename__ = "risk"

    id: Mapped[int] = id_column("risk_seq")
    code: Mapped[str] = code_column()
    project_id: Mapped[int] = mapped_column(IdType, ForeignKey("project.id"), nullable=False)
    title_en: Mapped[str] = mapped_column(String(500), nullable=False)
    title_ar: Mapped[str] = mapped_column(String(500), nullable=False)
    category: Mapped[str] = mapped_column(String(20), nullable=False)
    probability: Mapped[int] = mapped_column(Integer, nullable=False)
    impact: Mapped[int] = mapped_column(Integer, nullable=False)
    owner_name: Mapped[str | None] = mapped_column(String(160))
    mitigation_en: Mapped[str | None] = mapped_column(Text)
    mitigation_ar: Mapped[str | None] = mapped_column(Text)
    mitigation_due_date: Mapped[date | None] = mapped_column(Date)
    status_code: Mapped[str] = mapped_column(String(30), nullable=False)

    @property
    def score(self) -> int:
        return self.probability * self.impact


class Issue(AuditedMixin, ArchivableMixin, Base):
    __tablename__ = "issue"

    id: Mapped[int] = id_column("issue_seq")
    code: Mapped[str] = code_column()
    project_id: Mapped[int] = mapped_column(IdType, ForeignKey("project.id"), nullable=False)
    title_en: Mapped[str] = mapped_column(String(500), nullable=False)
    title_ar: Mapped[str] = mapped_column(String(500), nullable=False)
    severity: Mapped[str] = mapped_column(String(10), nullable=False)
    owner_name: Mapped[str | None] = mapped_column(String(160))
    raised_date: Mapped[date] = mapped_column(Date, nullable=False)
    target_date: Mapped[date | None] = mapped_column(Date)
    is_escalated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status_code: Mapped[str] = mapped_column(String(30), nullable=False)
    resolution_en: Mapped[str | None] = mapped_column(Text)
    resolution_ar: Mapped[str | None] = mapped_column(Text)
