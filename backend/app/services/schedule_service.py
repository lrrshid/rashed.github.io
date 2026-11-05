"""Scheduled reports: recurring reports by frequency, language and format, written to a folder.

The system runs on an isolated (air-gapped) network: nothing is e-mailed. `flask --app wsgi run-schedules` (run it
from the server's task scheduler, e.g. every day at 06:00) generates every due report as its owner would see it (same
permissions and department scope) and writes the file to

    <REPORTS_OUTPUT_DIR>/<schedule output folder>/<run date>/<report file>

REPORTS_OUTPUT_DIR is a local folder or a shared folder on the local network. Every run is recorded in the report
history, where the file can also be downloaded from the application."""
from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import select

from ..exceptions import NotFound, ValidationFailed
from ..models import AppUser, ReportRun, ReportSchedule, ReportTemplate
from ..models.reports import FILE_FORMATS, FREQUENCIES, LANGUAGES
from ..schemas.dto import record_meta, sid
from ..security.auth import PERM_REPORTS_SCHEDULE, can_admin, require_permission, user_load_options
from . import context, crud, report_export, report_service

# A folder name: letters (Latin or Arabic), digits, spaces, - and _. No dots or slashes, so it cannot leave the
# reports output directory.
FOLDER_RE = re.compile(r"^[\w؀-ۿ][\w؀-ۿ \-]{0,79}$")


def output_root() -> Path:
    return Path(context.settings().reports_dir)


def next_date(current: date, frequency: str) -> date:
    if frequency == "DAILY":
        return current + timedelta(days=1)
    if frequency == "WEEKLY":
        return current + timedelta(days=7)
    months = 1 if frequency == "MONTHLY" else 3
    month = current.month - 1 + months
    year = current.year + month // 12
    month = month % 12 + 1
    return date(year, month, min(current.day, 28))


def schedule_dto(s: ReportSchedule) -> dict:
    title = None
    if s.report_key:
        report = report_service._cat().get(s.report_key)
        title = {"en": report["titleEn"], "ar": report["titleAr"]} if report else None
    elif s.template_id:
        tpl = context.session().get(ReportTemplate, s.template_id)
        title = {"en": tpl.name, "ar": tpl.name} if tpl else None
    return {"id": sid(s.id), "name": s.name, "reportKey": s.report_key, "templateId": sid(s.template_id), "report": title,
            "frequency": s.frequency, "language": s.language, "format": s.file_format, "runTime": s.run_time,
            "outputFolder": s.output_folder, "nextRunDate": s.next_run_date.isoformat(), "active": bool(s.is_active),
            "ownerId": sid(s.owner_id), **record_meta(s)}


def list_schedules(actor) -> list[dict]:
    require_permission(actor, PERM_REPORTS_SCHEDULE)
    query = select(ReportSchedule).order_by(ReportSchedule.next_run_date, ReportSchedule.id)
    if not can_admin(actor):
        query = query.where(ReportSchedule.owner_id == actor.id)
    return [schedule_dto(s) for s in context.session().scalars(query)]


def _validate(data: dict) -> dict:
    out = {}
    if "name" in data:
        name = (data["name"] or "").strip()
        if not 1 <= len(name) <= 120:
            raise ValidationFailed.field("name", "Must be 1 to 120 characters.")
        out["name"] = name
    if "reportKey" in data:
        if data["reportKey"] and data["reportKey"] not in report_service._cat():
            raise ValidationFailed.field("reportKey", "Unknown report.")
        out["report_key"] = data["reportKey"] or None
    if "templateId" in data:
        out["template_id"] = int(data["templateId"]) if data["templateId"] else None
    for key, attr, allowed in (("frequency", "frequency", FREQUENCIES), ("language", "language", LANGUAGES),
                               ("format", "file_format", FILE_FORMATS)):
        if key in data:
            value = str(data[key] or "").upper()
            if value not in allowed:
                raise ValidationFailed.field(key, f"Must be one of: {', '.join(allowed)}.")
            out[attr] = value
    if "runTime" in data:
        if not re.fullmatch(r"([01][0-9]|2[0-3]):[0-5][0-9]", str(data["runTime"] or "")):
            raise ValidationFailed.field("runTime", "Use HH:MM (24-hour).")
        out["run_time"] = data["runTime"]
    if "outputFolder" in data:
        folder = str(data["outputFolder"] or "").strip()
        if not FOLDER_RE.match(folder):
            raise ValidationFailed.field("outputFolder", "Use a folder name of letters, digits, spaces, - and _ only.")
        out["output_folder"] = folder
    if "nextRunDate" in data:
        try:
            out["next_run_date"] = date.fromisoformat(str(data["nextRunDate"]))
        except ValueError:
            raise ValidationFailed.field("nextRunDate", "Use the date format YYYY-MM-DD.") from None
    if "active" in data:
        out["is_active"] = 1 if data["active"] else 0
    return out


def save_schedule(actor, data: dict, schedule_id: int | None = None) -> dict:
    require_permission(actor, PERM_REPORTS_SCHEDULE)
    values = _validate(data)
    if schedule_id is None:
        values.setdefault("next_run_date", context.today() + timedelta(days=1))
        values.setdefault("is_active", 1)
        required = ("name", "frequency", "language", "file_format", "run_time", "output_folder")
        missing = [k for k in required if k not in values]
        if missing or not (values.get("report_key") or values.get("template_id")):
            raise ValidationFailed("Please correct the highlighted fields.",
                                   [{"field": k, "message": "This field is required."} for k in missing or ["reportKey"]])
        s = ReportSchedule(owner_id=actor.id, **values)
        crud.create(actor, s, PERM_REPORTS_SCHEDULE)
    else:
        s = context.session().get(ReportSchedule, schedule_id)
        if s is None or (s.owner_id != actor.id and not can_admin(actor)):
            raise NotFound("Schedule was not found.")
        crud.update(actor, s, values, PERM_REPORTS_SCHEDULE, data.get("version"), data.get("reason"), department_ids=(None,))
    return schedule_dto(s)


def run_due(today: date | None = None) -> list[dict]:
    """Generate every active schedule due today or earlier. Returns what was produced."""
    session = context.session()
    today = today or context.today()
    produced = []
    due = list(session.scalars(select(ReportSchedule).where(ReportSchedule.is_active == 1,
                                                            ReportSchedule.next_run_date <= today)))
    for s in due:
        owner = session.scalars(select(AppUser).where(AppUser.id == s.owner_id).options(*user_load_options())).one()
        if not owner.active:
            continue
        key = s.report_key or f"template-{s.template_id}"
        result = report_service.run_report(owner, key, s.language, s.file_format, log=False)
        if s.file_format == "HTML":
            content = _html(result).encode("utf-8")
            name = report_export.file_name(result, "html")
        else:
            exporter, _, ext = report_export.EXPORTERS[s.file_format]
            content = exporter(result, s.language)
            name = report_export.file_name(result, ext)
        relative = Path(s.output_folder) / today.isoformat() / name
        target = output_root() / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        report_service.log_run(owner, result, s.language, s.file_format, schedule_id=s.id, file_name=relative.as_posix())
        s = session.get(ReportSchedule, s.id)
        s.next_run_date = next_date(max(s.next_run_date, today), s.frequency)
        s.updated_at = context.now()
        session.commit()
        produced.append({"schedule": s.name, "file": str(target)})
    return produced


def stored_file(actor, run_id: int) -> tuple[ReportRun, Path]:
    """The file a scheduled run wrote, for download from the report history (owner or administrator)."""
    run = context.session().get(ReportRun, run_id)
    if run is None or not run.file_name or run.schedule_id is None or (run.run_by != actor.id and not can_admin(actor)):
        raise NotFound("That report file was not found.")
    root = output_root().resolve()
    path = (root / run.file_name).resolve()
    if root not in path.parents or not path.is_file():
        raise NotFound("That report file is no longer in the reports folder.")
    return run, path


def _html(result: dict) -> str:
    from html import escape
    parts = [f"<h1>{escape(result['titleEn'])}</h1><p>{escape(result['header']['classification'])}</p>"]
    for s in result["sections"]:
        if s["kind"] == "table":
            parts.append(f"<h2>{escape(s.get('title') or '')}</h2><table border='1' cellpadding='4'><tr>"
                         + "".join(f"<th>{escape(c['label'])}</th>" for c in s["columns"]) + "</tr>"
                         + "".join("<tr>" + "".join(f"<td>{escape(str(r.get(c['key']) if r.get(c['key']) is not None else ''))}</td>"
                                                    for c in s["columns"]) + "</tr>" for r in s["rows"]) + "</table>")
    return "<!doctype html><meta charset='utf-8'>" + "".join(parts)
