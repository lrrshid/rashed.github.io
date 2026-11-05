"""Versioned documents and alert rules / acknowledgements."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import UTCDateTime
from .base import ArchivableMixin, AuditedMixin, Base, IdType, code_column, id_column, user_fk

DOC_TYPES = ("REPORT", "SPECIFICATION", "CONTRACT", "TEST_REPORT", "MANUAL", "CERTIFICATE", "CORRESPONDENCE",
             "PRESENTATION", "DATASHEET", "OTHER")
DOC_ENTITIES = ("CAPABILITY_MODEL", "ASSET", "PROJECT", "TEST_EVENT", "MAINTENANCE_ORDER", "ORGANIZATION", "CONTRACT",
                "CAPABILITY_REQUIREMENT")


class Document(AuditedMixin, ArchivableMixin, Base):
    __tablename__ = "document"

    id: Mapped[int] = id_column("document_seq")
    code: Mapped[str] = code_column()
    title_en: Mapped[str] = mapped_column(String(200), nullable=False)
    title_ar: Mapped[str] = mapped_column(String(200), nullable=False)
    doc_type: Mapped[str] = mapped_column(String(20), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    entity_id: Mapped[int] = mapped_column(IdType, nullable=False)
    department_id: Mapped[int | None] = mapped_column(IdType, ForeignKey("department.id"))
    current_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class DocumentVersion(Base):
    __tablename__ = "document_version"

    id: Mapped[int] = id_column("document_version_seq")
    document_id: Mapped[int] = mapped_column(IdType, ForeignKey("document.id"), nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    file_name: Mapped[str] = mapped_column(String(200), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    note: Mapped[str | None] = mapped_column(String(500))
    uploaded_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    uploaded_by: Mapped[int] = user_fk()


class AlertRule(AuditedMixin, Base):
    __tablename__ = "alert_rule"

    id: Mapped[int] = id_column("alert_rule_seq")
    alert_type: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    role_codes: Mapped[str] = mapped_column(String(500), nullable=False)
    is_enabled: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    days_ahead: Mapped[int | None] = mapped_column(Integer)

    @property
    def roles(self) -> list[str]:
        return [r for r in self.role_codes.split(",") if r]


class AlertAck(Base):
    __tablename__ = "alert_ack"

    alert_key: Mapped[str] = mapped_column(String(120), primary_key=True)
    user_id: Mapped[int] = mapped_column(IdType, ForeignKey("app_user.id"), primary_key=True)
    acked_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
