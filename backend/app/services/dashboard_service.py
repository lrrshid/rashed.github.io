"""GET /dashboard: the capability position in one answer. KPIs with month / quarter / year trends (METRIC_SNAPSHOT),
the leadership-attention list, status distribution, completion, gap heatmap, the department x category matrix,
site distribution and the project portfolio overview. Every figure carries how to open its records."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import timedelta

from sqlalchemy import func, select

from ..models import Asset, CapabilityModel, Department, Issue, Project, Site
from ..schemas.dto import sid
from ..security.auth import ALL_DEPARTMENTS, department_scope, require_department_access
from . import context, lookup_service as lk, metrics_service, project_health, settings_service, snapshot_service


def _trend(metric: str, value: float, department_id: int | None) -> dict:
    today = context.today()
    out = {}
    for key, days in (("m", 30), ("q", 91), ("y", 365)):
        past = snapshot_service.value_on_or_before(metric, department_id, today - timedelta(days=days))
        out[key] = None if past is None else round(value - past, 1)
    return out


def _projects(actor, department_id: int | None) -> list[Project]:
    query = select(Project).where(Project.archived_at.is_(None))
    scope = department_scope(actor)
    if scope is not ALL_DEPARTMENTS:
        query = query.where(Project.department_id.in_(sorted(scope) or [-1]))
    if department_id:
        query = query.where(Project.department_id == department_id)
    return list(context.session().scalars(query.order_by(Project.code)))


def dashboard(actor, department_id: int | None = None) -> dict:
    if department_id:
        require_department_access(actor, department_id, "Department was not found.")
    values = snapshot_service.current_values(actor, department_id)
    dept_filter = {"department": [sid(department_id)]} if department_id else {}

    def kpi(metric: str, drill: dict | None = None, link: str | None = None, lower_is_better: bool = False):
        return {"value": values[metric], "trend": _trend(metric, values[metric], department_id),
                "drill": {**dept_filter, **drill} if drill is not None else None, "link": link,
                "lowerIsBetter": lower_is_better}

    projects = _projects(actor, department_id)
    ctx = project_health.HealthContext([p.id for p in projects])
    today = context.today()
    rows = []
    for p in projects:
        hl = project_health.health(p, ctx)
        rows.append((p, hl))
    active = [(p, hl) for p, hl in rows if p.status_code not in ctx.terminal]
    due = lambda n: [p for p, _ in active if (p.forecast_end_date or p.target_end_date) and  # noqa: E731
                     0 <= ((p.forecast_end_date or p.target_end_date) - today).days <= n]
    project_kpis = {
        "activeProjects": {"value": len(active), "link": "/projects?view=active"},
        "devProjects": {"value": sum(1 for p, _ in active if p.status_code == "DEVELOPMENT"), "link": "/projects?status=DEVELOPMENT"},
        "testProjects": {"value": sum(1 for p, _ in active if p.status_code in ("TESTING", "FIELD_TRIALS", "EVALUATION")),
                         "link": "/projects?status=TESTING,FIELD_TRIALS,EVALUATION"},
        "delayedProjects": {"value": sum(1 for _, hl in active if hl["delayDays"] > 0), "link": "/projects?view=delayed",
                            "lowerIsBetter": True},
        "due30": {"value": len(due(30)), "link": "/projects?view=due30"},
        "due90": {"value": len(due(90)), "link": "/projects?view=due90"},
    }
    for key, metric in (("activeProjects", "projects_active"), ("delayedProjects", "projects_delayed")):
        project_kpis[key]["trend"] = _trend(metric, project_kpis[key]["value"], department_id)

    requirements = metrics_service.requirement_metrics(actor, department_id)
    attention = []
    for r in requirements:
        if r["critical"]:
            no_project = not any(p["countsInForecast"] for p in r["projects"])
            attention.append({"kind": "GAP", "severity": "RED", "link": f"/requirements/{r['id']}",
                              "textEn": f"Critical gap: {r['nameEn']} — shortage {r['forecastGap']}"
                                        + (", no approved project" if no_project else ""),
                              "textAr": f"فجوة حرجة: {r['nameAr']} — نقص {r['forecastGap']}"
                                        + ("، دون مشروع معتمد" if no_project else "")})
    for p, hl in sorted(active, key=lambda x: -x[1]["delayDays"]):
        if hl["overall"] == "RED":
            worst = next((v for v in hl["indicators"].values() if v["rag"] == "RED"), None)
            attention.append({"kind": "PROJECT", "severity": "RED", "link": f"/projects/{p.id}",
                              "textEn": f"{p.code} {p.name_en}: {worst['reasonEn'] if worst else ''}",
                              "textAr": f"{p.code} {p.name_ar}: {worst['reasonAr'] if worst else ''}"})
    escalated = [i for i in context.session().scalars(select(Issue).where(Issue.archived_at.is_(None), Issue.is_escalated == 1))
                 if i.status_code not in project_health.terminal_codes("ISSUE")
                 and any(i.project_id == p.id for p, _ in active)]
    for i in escalated:
        attention.append({"kind": "ISSUE", "severity": "AMBER", "link": f"/issues?focus={i.id}",
                          "textEn": f"{i.code} escalated: {i.title_en}", "textAr": f"{i.code} مصعّدة: {i.title_ar}"})

    counts = metrics_service.asset_status_counts(actor, department_id)
    status_rows = [{"status": code, "count": counts.get(code, 0), "drill": {**dept_filter, "status": [code]}}
                   for code in lk.statuses("ASSET")]

    completion = metrics_service.completion(actor, "department")
    groups = [g for g in completion["groups"] if not department_id or g["department"]["id"] == sid(department_id)]
    heatmap = metrics_service.gap_heatmap(actor)
    matrix = metrics_service.matrix(actor)
    if department_id:
        heatmap["departments"] = [d for d in heatmap["departments"] if d["id"] == sid(department_id)]
        heatmap["cells"] = [c for c in heatmap["cells"] if c["departmentId"] == sid(department_id)]
        matrix["departments"] = [d for d in matrix["departments"] if d["id"] == sid(department_id)]
        matrix["cells"] = [c for c in matrix["cells"] if c["departmentId"] == sid(department_id)]

    # Sites: operational assets vs not ready / maintenance per site.
    operational = set(settings_service.get("assets.operational_statuses"))
    available = set(settings_service.get("assets.available_statuses"))
    query = (select(Asset.site_id, Asset.status_code, func.count()).where(Asset.archived_at.is_(None))
             .group_by(Asset.site_id, Asset.status_code))
    scope = department_scope(actor)
    if scope is not ALL_DEPARTMENTS:
        query = query.where(Asset.department_id.in_(sorted(scope) or [-1]))
    if department_id:
        query = query.where(Asset.department_id == department_id)
    per_site = defaultdict(lambda: {"ready": 0, "notReady": 0})
    for site_id, status, n in context.session().execute(query):
        if site_id is None:
            continue
        if status in operational:
            per_site[site_id]["ready"] += n
        elif status in available:
            per_site[site_id]["notReady"] += n
    sites = [{"site": lk.ref_id(Site, sid_), **v, "drill": {**dept_filter, "site": [sid(sid_)], "statusGroup": "AVAILABLE"}}
             for sid_, v in sorted(per_site.items(), key=lambda kv: -(kv[1]["ready"] + kv[1]["notReady"]))]

    by_status = Counter(p.status_code for p in projects)
    by_health = Counter(hl["overall"] for _, hl in active)
    quarters = defaultdict(lambda: Counter())
    for p, hl in active:
        end = p.forecast_end_date or p.target_end_date
        if end:
            quarters[f"{end.year}-Q{(end.month - 1) // 3 + 1}"][hl["overall"]] += 1

    return {
        "asOf": today.isoformat(),
        "department": lk.ref_id(Department, department_id),
        "inventory": {
            "capabilities": kpi("capabilities_total", None, "/capabilities?tab=models"),
            "assets": kpi("assets_total", {}),
            "ready": kpi("assets_operational", {"statusGroup": "OPERATIONAL"}),
            "maintenance": kpi("assets_maintenance", {"status": ["UNDER_MAINTENANCE"]}, lower_is_better=True),
            "notReady": kpi("assets_not_ready", {"status": ["NOT_READY", "TEMP_NOT_READY"]}, lower_is_better=True),
            "awaiting": kpi("assets_awaiting_replacement", {"status": ["AWAITING_REPLACEMENT"]}, lower_is_better=True),
            "writtenOff": kpi("assets_written_off", {"status": ["WRITTEN_OFF"]}, lower_is_better=True),
        },
        "pipeline": {
            "acquisition": kpi("assets_under_acquisition", {"status": ["UNDER_ACQUISITION"]}),
            "development": kpi("assets_under_development", {"status": ["UNDER_DEVELOPMENT"]}),
            "test": kpi("assets_under_test", {"status": ["UNDER_TEST"]}),
            "criticalGaps": {**kpi("critical_gaps", None, "/gaps", lower_is_better=True)},
        },
        "portfolio": project_kpis,
        "attention": attention,
        "statusDistribution": status_rows,
        "completion": {"total": completion["total"], "groups": groups},
        "heatmap": heatmap,
        "matrix": matrix,
        "sites": sites,
        "projects": {
            "byStatus": [{"status": code, "count": n} for code, n in by_status.items()],
            "byHealth": {k: by_health.get(k, 0) for k in ("GREEN", "AMBER", "RED")},
            "byQuarter": [{"quarter": q, **{k: c.get(k, 0) for k in ("GREEN", "AMBER", "RED")}}
                          for q, c in sorted(quarters.items())],
            "total": len(projects),
        },
    }
