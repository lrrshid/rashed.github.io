"""Project health: six independent RAG indicators, each with its stated reason, and the overall health (the worst).

  schedule     days the forecast (or today) is past the target end date   (Settings: health.schedule)
  budget       spend + commitments against the budget                      (Settings: health.budget)
  risks        the highest open risk score (probability x impact)          (Settings: health.risk)
  testing      the latest test results of the project's models; open critical issues while testing
  scope        recorded by the project manager (PROJECT_HEALTH_NOTE), with its reason
  procurement  recorded by the project manager (PROJECT_HEALTH_NOTE), with its reason

Everything is derived at read time from the source records, never stored, so it cannot go stale.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date

from sqlalchemy import select

from ..models import Issue, Project, ProjectHealthNote, Risk, StatusDef
from . import context, settings_service

DIMENSIONS = ("SCHEDULE", "BUDGET", "SCOPE", "TESTING", "RISKS", "PROCUREMENT")
_ORDER = {"GREEN": 0, "GREY": 0, "AMBER": 1, "RED": 2}


def terminal_codes(domain: str) -> set[str]:
    return {s.code for s in context.session().scalars(
        select(StatusDef).where(StatusDef.domain == domain, StatusDef.is_terminal == 1))}


def delay_days(project: Project, today: date, terminal: set[str]) -> int:
    target = project.target_end_date
    if project.status_code in terminal or target is None:
        if project.actual_end_date and target:
            return max((project.actual_end_date - target).days, 0)
        return 0
    forecast = project.forecast_end_date or target
    return max((forecast - target).days, (today - target).days, 0)


class HealthContext:
    """Loads, once, what the indicators of many projects need."""

    def __init__(self, project_ids: list[int] | None = None):
        session = context.session()
        self.today = context.today()
        self.terminal = terminal_codes("PROJECT")
        self.risk_terminal = terminal_codes("RISK")
        self.issue_terminal = terminal_codes("ISSUE")
        self.schedule = settings_service.get("health.schedule")
        self.budget = settings_service.get("health.budget")
        self.risk = settings_service.get("health.risk")
        risk_q = select(Risk).where(Risk.archived_at.is_(None))
        issue_q = select(Issue).where(Issue.archived_at.is_(None))
        note_q = select(ProjectHealthNote)
        if project_ids is not None:
            risk_q = risk_q.where(Risk.project_id.in_(project_ids or [-1]))
            issue_q = issue_q.where(Issue.project_id.in_(project_ids or [-1]))
            note_q = note_q.where(ProjectHealthNote.project_id.in_(project_ids or [-1]))
        self.risks = defaultdict(list)
        for r in session.scalars(risk_q):
            if r.status_code not in self.risk_terminal:
                self.risks[r.project_id].append(r)
        self.issues = defaultdict(list)
        for i in session.scalars(issue_q):
            if i.status_code not in self.issue_terminal:
                self.issues[i.project_id].append(i)
        self.notes = defaultdict(dict)
        for n in session.scalars(note_q):
            self.notes[n.project_id][n.dimension] = n
        self.tests = {}  # project_id -> (rag, reason); filled by the testing module when it is present
        try:
            from . import testing_service
            self.tests = testing_service.project_test_health(project_ids)
        except (ImportError, AttributeError):
            pass

    def risk_level(self, score: int) -> str:
        if score >= self.risk["critical"]:
            return "CRITICAL"
        if score >= self.risk["high"]:
            return "HIGH"
        if score >= self.risk["medium"]:
            return "MEDIUM"
        return "LOW"


def _ind(rag: str, en: str, ar: str) -> dict:
    return {"rag": rag, "reasonEn": en, "reasonAr": ar}


def health(project: Project, ctx: HealthContext) -> dict:
    out = {}
    days = delay_days(project, ctx.today, ctx.terminal)
    if project.status_code in ctx.terminal:
        out["SCHEDULE"] = _ind("GREEN", "Project closed.", "المشروع مغلق.")
    elif days >= ctx.schedule["red_days"]:
        out["SCHEDULE"] = _ind("RED", f"Forecast completion {days} days after the target date.",
                               f"الإنجاز المتوقع بعد الموعد المستهدف بـ {days} يوماً.")
    elif days >= max(ctx.schedule["amber_days"], 1):
        out["SCHEDULE"] = _ind("AMBER", f"Forecast completion {days} days after the target date.",
                               f"الإنجاز المتوقع بعد الموعد المستهدف بـ {days} يوماً.")
    else:
        out["SCHEDULE"] = _ind("GREEN", "On schedule.", "ضمن الجدول الزمني.")

    if project.budget:
        used = (project.actual_spend or 0) + (project.committed or 0)
        pct = round(100 * used / project.budget)
        over = pct - 100
        en = f"Spend and commitments at {pct}% of the budget."
        ar = f"الصرف والالتزامات عند {pct}% من الميزانية."
        rag = "RED" if over > ctx.budget["red_pct"] else "AMBER" if over > ctx.budget["amber_pct"] else "GREEN"
        out["BUDGET"] = _ind(rag, en, ar)
    else:
        out["BUDGET"] = _ind("GREY", "No budget recorded.", "لا توجد ميزانية مسجلة.")

    for dim in ("SCOPE", "PROCUREMENT"):
        note = ctx.notes[project.id].get(dim)
        if note:
            out[dim] = _ind(note.rag, note.reason_en or "", note.reason_ar or note.reason_en or "")
        else:
            out[dim] = _ind("GREEN", "No issue recorded.", "لا توجد ملاحظات مسجلة.")

    risks = ctx.risks.get(project.id, [])
    if risks:
        top = max(risks, key=lambda r: r.probability * r.impact)
        score = top.probability * top.impact
        level = ctx.risk_level(score)
        rag = "RED" if level == "CRITICAL" else "AMBER" if level == "HIGH" else "GREEN"
        out["RISKS"] = _ind(rag, f"{top.code} score {score} ({level.lower()}): {top.title_en}",
                            f"{top.code} درجة {score}: {top.title_ar}")
    else:
        out["RISKS"] = _ind("GREEN", "No open risks.", "لا توجد مخاطر مفتوحة.")

    if project.id in ctx.tests:
        rag, en, ar = ctx.tests[project.id]
        out["TESTING"] = _ind(rag, en, ar)
    else:
        critical = [i for i in ctx.issues.get(project.id, []) if i.severity == "CRITICAL"]
        if critical:
            out["TESTING"] = _ind("AMBER", f"Open critical issue {critical[0].code}.", f"مشكلة حرجة مفتوحة {critical[0].code}.")
        else:
            out["TESTING"] = _ind("GREY", "No test results recorded.", "لا توجد نتائج اختبار مسجلة.")

    worst = max((v["rag"] for v in out.values()), key=lambda r: _ORDER[r])
    return {"overall": "GREEN" if worst == "GREY" else worst, "indicators": out, "delayDays": days}
