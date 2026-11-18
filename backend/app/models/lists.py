"""Configurable lists: departments, categories, sites, organisations, statuses, project types and their workflow
stages, technical specification fields. Changed in Settings without code; archived, never deleted."""
from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import ArchivableMixin, AuditedMixin, Base, IdType, NamedMixin, code_column, id_column


class Department(NamedMixin, AuditedMixin, ArchivableMixin, Base):
    __tablename__ = "department"

    id: Mapped[int] = id_column("department_seq")
    code: Mapped[str] = code_column()
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class CapabilityCategory(NamedMixin, AuditedMixin, ArchivableMixin, Base):
    __tablename__ = "capability_category"

    id: Mapped[int] = id_column("capability_category_seq")
    code: Mapped[str] = code_column()
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class Site(NamedMixin, AuditedMixin, ArchivableMixin, Base):
    __tablename__ = "site"

    id: Mapped[int] = id_column("site_seq")
    code: Mapped[str] = code_column()
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class OrgUnit(NamedMixin, AuditedMixin, ArchivableMixin, Base):
    """Organisational units that conduct tests: a directorate (no parent) and its sections (parent = the directorate).
    Two levels only (admin_service checks it)."""
    __tablename__ = "org_unit"

    id: Mapped[int] = id_column("org_unit_seq")
    code: Mapped[str] = code_column()
    parent_id: Mapped[int | None] = mapped_column(IdType, ForeignKey("org_unit.id"))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


ORG_KINDS = ("MANUFACTURER", "SUPPLIER", "BOTH")


class Organization(NamedMixin, AuditedMixin, ArchivableMixin, Base):
    __tablename__ = "organization"

    id: Mapped[int] = id_column("organization_seq")
    code: Mapped[str] = code_column()
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    country_en: Mapped[str | None] = mapped_column(String(80))
    country_ar: Mapped[str | None] = mapped_column(String(80))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


STATUS_DOMAINS = ("ASSET", "PROJECT", "MILESTONE", "RISK", "ISSUE", "TEST", "MAINTENANCE", "DEVELOPMENT")
COLORS = ("green", "amber", "red", "blue", "purple", "teal", "grey", "orange", "pink", "dark")


class StatusDef(NamedMixin, AuditedMixin, ArchivableMixin, Base):
    __tablename__ = "status_def"

    id: Mapped[int] = id_column("status_def_seq")
    # Column status_domain (DOMAIN is a keyword in Oracle 23ai); the attribute keeps the short name.
    domain: Mapped[str] = mapped_column("status_domain", String(20), nullable=False)
    code: Mapped[str] = mapped_column(String(30), nullable=False)
    color: Mapped[str] = mapped_column(String(10), nullable=False, default="grey")
    is_terminal: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class ProjectType(NamedMixin, AuditedMixin, ArchivableMixin, Base):
    __tablename__ = "project_type"

    id: Mapped[int] = id_column("project_type_seq")
    code: Mapped[str] = code_column(30)
    color: Mapped[str] = mapped_column(String(10), nullable=False, default="blue")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class WorkflowStage(NamedMixin, AuditedMixin, ArchivableMixin, Base):
    __tablename__ = "workflow_stage"

    id: Mapped[int] = id_column("workflow_stage_seq")
    project_type_id: Mapped[int] = mapped_column(IdType, ForeignKey("project_type.id"), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)


SPEC_SECTIONS = ("PERFORMANCE", "SENSORS", "COMMUNICATIONS", "ENVIRONMENT", "OTHER")
SPEC_TYPES = ("TEXT", "NUMBER", "BOOL")


class SpecField(NamedMixin, AuditedMixin, ArchivableMixin, Base):
    __tablename__ = "spec_field"

    id: Mapped[int] = id_column("spec_field_seq")
    category_id: Mapped[int] = mapped_column(IdType, ForeignKey("capability_category.id"), nullable=False)
    section: Mapped[str] = mapped_column(String(20), nullable=False)
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    unit: Mapped[str | None] = mapped_column(String(20))
    data_type: Mapped[str] = mapped_column(String(10), nullable=False)
    is_custom: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
