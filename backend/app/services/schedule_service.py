"""Scheduled reports: recurring reports by frequency, language, format and recipients.

`flask --app wsgi run-schedules` (run it daily from the server's task scheduler) generates every due report as its
owner would see it (same permissions and department scope), writes the file under data/reports/<date>/, records the
run, and moves the schedule to its next date. E-mail delivery to the recipients is not connected yet: the files and
the run log are the delivery record until an SMTP relay is configured."""
from __future__ import annotations

import re
from datetime import date, timedelta

from sqlalchemy import select

from ..core.config import DATA_DIR
from ..exceptions import NotFound, ValidationFailed
from ..models import AppUser, ReportSchedule, ReportTemplate
from ..models.reports import FILE_FORMATS, FREQUENCIES, LANGUAGES
from ..schemas.dto import record_meta, sid
from ..security.auth import PERM_REPORTS_SCHEDULE, can_admin, require_permission, user_load_options
from . import context, crud, report_export, report_service

EMAIL_RE = re.compile(r"^[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+$")


def next_date(current: date, frequency: str) -> date:
    if frequency == "DAILY":
        return current + timedelta(days=1)
    if frequency == "WEEKLY":
        return current + timedelta(days=7)
    months = 1 if frequency == "MONTHLY" else 3
    month = current.month - 1 + months
    year = current.year + month // 12
    month = month % 12 + 1
    day = min(current.day, 28)
    return date(year, month, day)


def schedule_dto(s: ReportSchedule) -> dict:
    title = None
    if s.report_key:
        report = report_service._cat().get(s.report_key)
        title = {"en": report["titleEn"], "ar": report["titleAr"]} if report else None
    elif s.template_id:
        tpl = context.session().get(ReportTemplate, s.template_id)
        title = {"en": tpl.name, "ar": tpl.name} if tpl else None
    return {"id": sid(s.id), "name": s.name, "reportKey": s.report_key, "templateId": sid(s.template_id), "report": title,
            "frequency": s.frequency, "language": s.language, "format": s.file_format, "sendTime": s.send_time,
            "recipients": s.recipients.split(","), "nextRunDate": s.next_run_date.isoformat(), "active": bool(s.is_active),
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
    if "sendTime" in data:
        if not re.fullmatch(r"([01][0-9]|2[0-3]):[0-5][0-9]", str(data["sendTime"] or "")):
            raise ValidationFailed.field("sendTime", "Use HH:MM (24-hour).")
        out["send_time"] = data["sendTime"]
    if "recipients" in data:
        recipients = [r.strip() for r in (data["recipients"] or []) if r and r.strip()]
        if not recipients or any(not EMAIL_RE.match(r) for r in recipients):
            raise ValidationFailed.field("recipients", "Give one or more e-mail addresses.")
        joined = ",".join(recipients)
        if len(joined) > 1000:
            raise ValidationFailed.field("recipients", "Too many recipients.")
        out["recipients"] = joined
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
        required = ("name", "frequency", "language", "file_format", "send_time", "recipients")
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


def run_due(today: date | None = None, out_dir=None) -> list[dict]:
    """Generate every active schedule due today or earlier. Returns what was produced."""
    session = context.session()
    today = today or context.today()
    out_dir = out_dir or (DATA_DIR / "reports" / today.isoformat())
    produced = []
    due = list(session.scalars(select(ReportSchedule).where(ReportSchedule.is_active == 1,
                                                            ReportSchedule.next_run_date <= today)))
    for s in due:
        owner = session.scalars(select(AppUser).where(AppUser.id == s.owner_id).options(*user_load_options())).one()
        if not owner.active:
            continue
        lang = "BILINGUAL" if s.language == "BILINGUAL" else s.language
        key = s.report_key or f"template-{s.template_id}"
        result = report_service.run_report(owner, key, lang, s.file_format, log=False)
        if s.file_format == "HTML":
            content = _html(result).encode("utf-8")
            name = report_export.file_name(result, "html")
        else:
            exporter, _, ext = report_export.EXPORTERS[s.file_format]
            content = exporter(result, lang)
            name = report_export.file_name(result, ext)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / name).write_bytes(content)
        report_service.log_run(owner, result, lang, s.file_format, schedule_id=s.id, file_name=name)
        s = session.get(ReportSchedule, s.id)
        s.next_run_date = next_date(max(s.next_run_date, today), s.frequency)
        s.updated_at = context.now()
        session.commit()
        produced.append({"schedule": s.name, "file": str(out_dir / name), "recipients": s.recipients.split(",")})
    return produced


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
