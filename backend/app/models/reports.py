"""Custom report templates, scheduled reports, report run log."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import UTCDateTime
from .base import ArchivableMixin, AuditedMixin, Base, IdType, id_column, user_fk

FREQUENCIES = ("DAILY", "WEEKLY", "MONTHLY", "QUARTERLY")
LANGUAGES = ("EN", "AR", "BILINGUAL")
FILE_FORMATS = ("XLSX", "CSV", "PPTX", "HTML")


class ReportTemplate(AuditedMixin, ArchivableMixin, Base):
    __tablename__ = "report_template"

    id: Mapped[int] = id_column("report_template_seq")
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    owner_id: Mapped[int] = user_fk()
    is_shared: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    definition_json: Mapped[str] = mapped_column(Text, nullable=False)


class ReportSchedule(AuditedMixin, Base):
    __tablename__ = "report_schedule"

    id: Mapped[int] = id_column("report_schedule_seq")
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    report_key: Mapped[str | None] = mapped_column(String(80))
    template_id: Mapped[int | None] = mapped_column(IdType, ForeignKey("report_template.id"))
    frequency: Mapped[str] = mapped_column(String(10), nullable=False)
    language: Mapped[str] = mapped_column(String(10), nullable=False)
    file_format: Mapped[str] = mapped_column(String(10), nullable=False)
    run_time: Mapped[str] = mapped_column(String(5), nullable=False)
    output_folder: Mapped[str] = mapped_column(String(80), nullable=False)
    next_run_date: Mapped[date] = mapped_column(Date, nullable=False)
    is_active: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    owner_id: Mapped[int] = user_fk()


class ReportRun(Base):
    __tablename__ = "report_run"

    id: Mapped[int] = id_column("report_run_seq")
    report_key: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    schedule_id: Mapped[int | None] = mapped_column(IdType, ForeignKey("report_schedule.id"))
    run_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    run_by: Mapped[int] = user_fk()
    language: Mapped[str] = mapped_column(String(10), nullable=False)
    file_format: Mapped[str] = mapped_column(String(10), nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    file_name: Mapped[str | None] = mapped_column(String(300))  # path under the reports output directory
