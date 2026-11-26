"""Alert centre: sixteen automatic alert types, computed from the records each time (never stale), shown to the roles
the alert rules name (Settings > Alert rules), within the user's department scope, and acknowledged per user.

Every alert has a stable key (type + record id), so an acknowledgement survives until the condition changes into a
new alert (e.g. a milestone that slips again keeps its key and stays acknowledged; a new overdue milestone does not)."""
from __future__ import annotations

from sqlalchemy import select

from ..exceptions import NotFound, ValidationFailed
from ..models import (AlertAck, AlertRule, Asset, CapabilityModel, Contract, Issue, MaintenanceOrder, Milestone, Project,
                      Risk, TestEvent)
from ..security.auth import ALL_DEPARTMENTS, department_scope, require_admin
from . import audit_service, context, metrics_service, project_health, settings_service

# The roles of the organisation's structure (reference_data.ROLES) an alert goes to by default: the commander gets the
# strategic ones, the three section heads what concerns their work, the project manager the project ones and the user
# the field ones (maintenance, tests, spare parts, readiness). Changed in Settings > Alert rules.
_HEADS = "HEAD_CAP_DEV,HEAD_SECURITY,HEAD_UNMANNED"
# type -> (severity, default roles, default days ahead)
TYPES = {
    "PROJECT_DELAYED": ("HIGH", f"SYS_ADMIN,COMMANDER,{_HEADS},PROJECT_MGR", None),
    "MILESTONE_OVERDUE": ("HIGH", f"SYS_ADMIN,{_HEADS},PROJECT_MGR", None),
    "MILESTONE_DUE": ("INFO", "SYS_ADMIN,PROJECT_MGR", 14),
    "RISK_CRITICAL": ("CRITICAL", f"SYS_ADMIN,COMMANDER,{_HEADS},PROJECT_MGR", None),
    "MITIGATION_OVERDUE": ("HIGH", "SYS_ADMIN,PROJECT_MGR", None),
    "ISSUE_ESCALATED": ("HIGH", f"SYS_ADMIN,COMMANDER,{_HEADS},PROJECT_MGR", None),
    "ISSUE_OVERDUE": ("MEDIUM", "SYS_ADMIN,PROJECT_MGR", None),
    "MAINTENANCE_OVERDUE": ("HIGH", f"SYS_ADMIN,{_HEADS},USER", None),
    "SPARE_PARTS_SHORTAGE": ("MEDIUM", "SYS_ADMIN,USER", None),
    "WARRANTY_EXPIRING": ("MEDIUM", "SYS_ADMIN,HEAD_CAP_DEV,USER", 60),
    "CONTRACT_EXPIRING": ("MEDIUM", "SYS_ADMIN,HEAD_CAP_DEV,PROJECT_MGR", 90),
    "CRITICAL_GAP": ("CRITICAL", f"SYS_ADMIN,COMMANDER,{_HEADS}", None),
    "BUDGET_OVERRUN": ("HIGH", "SYS_ADMIN,COMMANDER,HEAD_CAP_DEV,PROJECT_MGR", None),
    "TEST_FAILED": ("HIGH", "SYS_ADMIN,HEAD_CAP_DEV,PROJECT_MGR,USER", 90),
    "TEST_UPCOMING": ("INFO", "SYS_ADMIN,USER", 30),
    "ASSET_NOT_READY": ("MEDIUM", f"SYS_ADMIN,{_HEADS},USER", None),
}
SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "INFO": 3}


def ensure_rules(actor) -> int:
    """Add the default rule of every alert type that has none (seeding and upgrades)."""
    session = context.session()
    have = {r.alert_type for r in session.scalars(select(AlertRule))}
    added = 0
    for alert_type, (_, roles, days) in TYPES.items():
        if alert_type in have:
            continue
        rule = AlertRule(alert_type=alert_type, role_codes=roles, is_enabled=1, days_ahead=days)
        context.stamp_create(rule, actor, context.now())
        session.add(rule)
        session.flush()
        audit_service.record(actor, "CREATE", rule, None, audit_service.snapshot(rule))
        added += 1
    return added


def _rules() -> dict[str, dict]:
    stored = {r.alert_type: r for r in context.session().scalars(select(AlertRule))}
    out = {}
    for alert_type, (severity, roles, days) in TYPES.items():
        r = stored.get(alert_type)
        out[alert_type] = {"type": alert_type, "severity": severity,
                           "roles": r.roles if r else roles.split(","), "enabled": bool(r.is_enabled) if r else True,
                           "daysAhead": r.days_ahead if r else days, "version": r.version if r else 0,
                           "id": str(r.id) if r else None}
    return out


def _d(value) -> str:
    """Dates inside alert messages: dd/mm/yyyy, Western digits."""
    return value.strftime("%d/%m/%Y")


def _alert(alert_type, record_id, text_en, text_ar, link, department_id, when=None):
    return {"key": f"{alert_type}:{record_id}", "type": alert_type, "severity": TYPES[alert_type][0],
            "textEn": text_en, "textAr": text_ar, "link": link, "departmentId": department_id,
            "date": when.isoformat() if when else None}


def _all_alerts(rules: dict) -> list[dict]:
    session = context.session()
    today = context.today()
    out = []

    def days(alert_type):
        return rules[alert_type]["daysAhead"] or 0

    projects = list(session.scalars(select(Project).where(Project.archived_at.is_(None))))
    by_id = {p.id: p for p in projects}
    ctx = project_health.HealthContext([p.id for p in projects])
    budget_rule = settings_service.get("health.budget")
    for p in projects:
        if p.status_code in ctx.terminal:
            continue
        hl = project_health.health(p, ctx)
        if hl["delayDays"] > 0:
            out.append(_alert("PROJECT_DELAYED", p.id, f"{p.code} {p.name_en} is {hl['delayDays']} days late.",
                              f"{p.code} {p.name_ar} متأخر {hl['delayDays']} يوماً.", f"/projects/{p.id}", p.department_id,
                              p.forecast_end_date))
        if p.budget:
            pct = round(100 * ((p.actual_spend or 0) + (p.committed or 0)) / p.budget)
            if pct - 100 > budget_rule["amber_pct"]:
                out.append(_alert("BUDGET_OVERRUN", p.id, f"{p.code}: spend and commitments at {pct}% of budget.",
                                  f"{p.code}: الصرف والالتزامات عند {pct}% من الميزانية.", f"/projects/{p.id}", p.department_id))
    for m in session.scalars(select(Milestone).where(Milestone.archived_at.is_(None), Milestone.status_code != "COMPLETED")):
        p = by_id.get(m.project_id)
        if p is None or p.status_code in ctx.terminal:
            continue
        end = m.forecast_end_date or m.planned_end_date
        if end < today:
            out.append(_alert("MILESTONE_OVERDUE", m.id, f"{p.code} milestone «{m.name_en}» is {(today - end).days} days overdue.",
                              f"{p.code}: المرحلة «{m.name_ar}» متأخرة {(today - end).days} يوماً.",
                              f"/projects/{p.id}?tab=milestones", p.department_id, end))
        elif m.is_major and (end - today).days <= days("MILESTONE_DUE"):
            out.append(_alert("MILESTONE_DUE", m.id, f"{p.code} major milestone «{m.name_en}» due {_d(end)}.",
                              f"{p.code}: المرحلة الرئيسية «{m.name_ar}» مستحقة في {_d(end)}.",
                              f"/projects/{p.id}?tab=milestones", p.department_id, end))
    for r in session.scalars(select(Risk).where(Risk.archived_at.is_(None))):
        p = by_id.get(r.project_id)
        if p is None or r.status_code in ctx.risk_terminal:
            continue
        if ctx.risk_level(r.probability * r.impact) == "CRITICAL":
            out.append(_alert("RISK_CRITICAL", r.id, f"{r.code} ({p.code}) critical risk, score {r.probability * r.impact}: {r.title_en}",
                              f"{r.code} ({p.code}) خطر حرج، الدرجة {r.probability * r.impact}: {r.title_ar}",
                              f"/projects/{p.id}?tab=risks", p.department_id))
        if r.mitigation_due_date and r.mitigation_due_date < today:
            out.append(_alert("MITIGATION_OVERDUE", r.id, f"{r.code} ({p.code}) mitigation overdue since {_d(r.mitigation_due_date)}.",
                              f"{r.code} ({p.code}) إجراء المعالجة متأخر منذ {_d(r.mitigation_due_date)}.",
                              f"/projects/{p.id}?tab=risks", p.department_id, r.mitigation_due_date))
    issue_terminal = project_health.terminal_codes("ISSUE")
    for i in session.scalars(select(Issue).where(Issue.archived_at.is_(None))):
        p = by_id.get(i.project_id)
        if p is None or i.status_code in issue_terminal:
            continue
        if i.is_escalated:
            out.append(_alert("ISSUE_ESCALATED", i.id, f"{i.code} ({p.code}) requires escalation: {i.title_en}",
                              f"{i.code} ({p.code}) تتطلب التصعيد: {i.title_ar}", f"/projects/{p.id}?tab=issues", p.department_id))
        if i.target_date and i.target_date < today:
            out.append(_alert("ISSUE_OVERDUE", i.id, f"{i.code} ({p.code}) is past its target date.",
                              f"{i.code} ({p.code}) تجاوزت موعد الحل المستهدف.", f"/projects/{p.id}?tab=issues",
                              p.department_id, i.target_date))
    assets = {a.id: a for a in session.scalars(select(Asset).where(Asset.archived_at.is_(None)))}
    models = {m.id: m for m in session.scalars(select(CapabilityModel))}
    for mo in session.scalars(select(MaintenanceOrder).where(MaintenanceOrder.archived_at.is_(None),
                                                            MaintenanceOrder.status_code.notin_(("COMPLETED", "CANCELLED")))):
        a = assets.get(mo.asset_id)
        if a is None:
            continue
        if mo.expected_end_date and mo.expected_end_date < today:
            late = (today - mo.expected_end_date).days
            out.append(_alert("MAINTENANCE_OVERDUE", mo.id, f"{a.code} {mo.title_en} ({mo.code}) {late} days overdue.",
                              f"{a.code} {mo.title_ar} ({mo.code}) متأخرة {late} يوماً.", "/maintenance", a.department_id,
                              mo.expected_end_date))
        if mo.parts_shortage:
            out.append(_alert("SPARE_PARTS_SHORTAGE", mo.id, f"{a.code}: waiting for spare parts ({mo.parts_text or mo.code}).",
                              f"{a.code}: بانتظار قطع الغيار ({mo.parts_text or mo.code}).", "/maintenance", a.department_id))
    for a in assets.values():
        if a.warranty_end_date and 0 <= (a.warranty_end_date - today).days <= days("WARRANTY_EXPIRING"):
            out.append(_alert("WARRANTY_EXPIRING", a.id, f"{a.code} warranty ends {_d(a.warranty_end_date)}.",
                              f"ينتهي ضمان {a.code} في {_d(a.warranty_end_date)}.", f"/assets/{a.id}",
                              a.department_id, a.warranty_end_date))
        if a.status_code == "NOT_READY":
            name = models[a.model_id].name_en if a.model_id in models else ""
            name_ar = models[a.model_id].name_ar if a.model_id in models else ""
            out.append(_alert("ASSET_NOT_READY", a.id, f"{a.code} {name} is not ready.", f"{a.code} {name_ar} غير جاهز.",
                              f"/assets/{a.id}", a.department_id))
    for c in session.scalars(select(Contract).where(Contract.archived_at.is_(None))):
        if c.end_date and 0 <= (c.end_date - today).days <= days("CONTRACT_EXPIRING"):
            out.append(_alert("CONTRACT_EXPIRING", c.id, f"Contract {c.code} ends {_d(c.end_date)}.",
                              f"ينتهي العقد {c.code} في {_d(c.end_date)}.", "/search?q=" + c.code, None, c.end_date))
    for r in metrics_service.requirement_metrics(_SystemActor()):
        if r["critical"]:
            out.append(_alert("CRITICAL_GAP", r["id"], f"Critical gap: {r['nameEn']}, forecast shortage {r['forecastGap']}.",
                              f"فجوة حرجة: {r['nameAr']}، النقص المتوقع {r['forecastGap']}.", f"/requirements/{r['id']}",
                              int(r["department"]["id"])))
    for e in session.scalars(select(TestEvent).where(TestEvent.archived_at.is_(None))):
        if e.status_code == "FAILED" and 0 <= (today - e.test_date).days <= days("TEST_FAILED"):
            out.append(_alert("TEST_FAILED", e.id, f"{e.code} {e.title_en} failed.", f"{e.code} {e.title_ar}: غير ناجح.",
                              "/testing", e.department_id, e.test_date))
        if e.status_code == "PLANNED" and 0 <= (e.test_date - today).days <= days("TEST_UPCOMING"):
            out.append(_alert("TEST_UPCOMING", e.id, f"{e.code} {e.title_en} on {_d(e.test_date)}.",
                              f"{e.code} {e.title_ar} في {_d(e.test_date)}.", "/testing", e.department_id, e.test_date))
    return out


class _SystemActor:
    """Gap alerts are computed for every department; the reader's scope filters them afterwards."""
    permissions = frozenset()
    role = None
    department_ids = frozenset()


def alerts_for(actor, include_acked: bool = True) -> dict:
    rules = _rules()
    role = actor.role_code
    from flask import g
    preview = getattr(g, "view_as_role", None)
    if preview is not None:
        role = preview.code
    scope = department_scope(actor)
    acked = set(context.session().scalars(select(AlertAck.alert_key).where(AlertAck.user_id == actor.id)))
    items = []
    for a in _all_alerts(rules):
        rule = rules[a["type"]]
        if not rule["enabled"] or role not in rule["roles"]:
            continue
        if scope is not ALL_DEPARTMENTS and a["departmentId"] is not None and a["departmentId"] not in scope:
            continue
        a = {**a, "acknowledged": a["key"] in acked, "departmentId": str(a["departmentId"]) if a["departmentId"] else None}
        if a["acknowledged"] and not include_acked:
            continue
        items.append(a)
    items.sort(key=lambda a: (a["acknowledged"], SEVERITY_ORDER[a["severity"]], a["type"], a["key"]))
    counts = {s: sum(1 for a in items if a["severity"] == s and not a["acknowledged"]) for s in SEVERITY_ORDER}
    return {"items": items, "counts": counts, "open": sum(1 for a in items if not a["acknowledged"]),
            "acknowledged": sum(1 for a in items if a["acknowledged"])}


def acknowledge(actor, keys: list[str]) -> dict:
    session = context.session()
    for key in keys:
        if not (3 <= len(key) <= 120) or ":" not in key or key.split(":", 1)[0] not in TYPES:
            raise ValidationFailed.field("keys", f"{key!r} is not an alert.")
        if session.get(AlertAck, (key, actor.id)) is None:
            session.add(AlertAck(alert_key=key, user_id=actor.id, acked_at=context.now()))
    session.commit()
    return alerts_for(actor)


def list_rules(actor) -> list[dict]:
    require_admin(actor)
    return list(_rules().values())


def update_rule(actor, alert_type: str, roles: list[str], enabled: bool, days_ahead, version) -> dict:
    require_admin(actor)
    if alert_type not in TYPES:
        raise NotFound(f"Alert type {alert_type} was not found.")
    from ..models import AppRole
    known = {r.code for r in context.session().scalars(select(AppRole))}
    unknown = [r for r in roles if r not in known]
    if unknown:
        raise ValidationFailed.field("roles", f"Unknown role: {', '.join(unknown)}.")
    session = context.session()
    rule = session.scalar(select(AlertRule).where(AlertRule.alert_type == alert_type).with_for_update(of=AlertRule.id))
    if rule is None:
        ensure_rules(actor)
        rule = session.scalar(select(AlertRule).where(AlertRule.alert_type == alert_type))
    from . import crud
    crud.update(actor, rule, {"role_codes": ",".join(sorted(set(roles))), "is_enabled": 1 if enabled else 0,
                              "days_ahead": days_ahead}, "admin", version, None, department_ids=(None,))
    return _rules()[alert_type]

