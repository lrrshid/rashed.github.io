"""Point-in-time KPI values (METRIC_SNAPSHOT) for month / quarter / year trends.

`take(actor)` stores today's values (run daily: `flask take-snapshot`; the dashboard also takes one on its first view
of the day). The demo seeder adds twelve month-ends of plausible history behind today's real values."""
from __future__ import annotations

import random
from datetime import date, timedelta

from sqlalchemy import delete, select

from ..models import Asset, Department, MetricSnapshot, Project, StatusDef
from . import context, lookup_service as lk, metrics_service, settings_service

# metric key -> computed by current_values()
METRICS = ("assets_total", "assets_operational", "assets_available", "assets_maintenance", "assets_not_ready",
           "assets_awaiting_replacement", "assets_written_off", "assets_under_acquisition", "assets_under_development",
           "assets_under_test", "capabilities_total", "completion_current", "completion_forecast", "critical_gaps",
           "projects_active", "projects_delayed", "readiness_avg")


def project_flags(project: Project, today: date, terminal: set[str]) -> dict:
    target = project.target_end_date
    forecast = project.forecast_end_date or target
    done = project.status_code in terminal
    delay = 0
    if not done and target:
        delay = max((forecast - target).days if forecast else 0, (today - target).days)
    return {"active": not done, "delayed": delay > 0, "delayDays": max(delay, 0)}


def current_values(actor, department_id: int | None = None) -> dict[str, float]:
    counts = metrics_service.asset_status_counts(actor, department_id)
    available = set(settings_service.get("assets.available_statuses"))
    operational = set(settings_service.get("assets.operational_statuses"))
    completion = metrics_service.requirement_metrics(actor, department_id)
    totals = metrics_service._sum(completion)
    session = context.session()
    terminal = {s.code for s in session.scalars(select(StatusDef).where(StatusDef.domain == "PROJECT",
                                                                        StatusDef.is_terminal == 1))}
    query = select(Project).where(Project.archived_at.is_(None))
    if department_id:
        query = query.where(Project.department_id == department_id)
    from ..security.auth import ALL_DEPARTMENTS, department_scope
    scope = department_scope(actor)
    if scope is not ALL_DEPARTMENTS:
        query = query.where(Project.department_id.in_(sorted(scope) or [-1]))
    today = context.today()
    flags = [project_flags(p, today, terminal) for p in session.scalars(query)]
    readiness_query = select(Asset.readiness_operational).where(
        Asset.archived_at.is_(None), Asset.readiness_operational.is_not(None),
        Asset.status_code.in_(sorted(available)))
    if department_id:
        readiness_query = readiness_query.where(Asset.department_id == department_id)
    readiness = list(session.scalars(readiness_query))
    models = len({m for m in session.scalars(select(Asset.model_id).where(Asset.archived_at.is_(None)))})
    return {
        "assets_total": sum(counts.values()),
        "assets_operational": sum(n for s, n in counts.items() if s in operational),
        "assets_available": sum(n for s, n in counts.items() if s in available),
        "assets_maintenance": counts.get("UNDER_MAINTENANCE", 0),
        "assets_not_ready": counts.get("NOT_READY", 0) + counts.get("TEMP_NOT_READY", 0),
        "assets_awaiting_replacement": counts.get("AWAITING_REPLACEMENT", 0),
        "assets_written_off": counts.get("WRITTEN_OFF", 0),
        "assets_under_acquisition": counts.get("UNDER_ACQUISITION", 0),
        "assets_under_development": counts.get("UNDER_DEVELOPMENT", 0),
        "assets_under_test": counts.get("UNDER_TEST", 0),
        "capabilities_total": models,
        "completion_current": totals["currentPct"] or 0,
        "completion_forecast": totals["forecastPct"] or 0,
        "critical_gaps": totals["criticalGaps"],
        "projects_active": sum(1 for f in flags if f["active"]),
        "projects_delayed": sum(1 for f in flags if f["delayed"]),
        "readiness_avg": round(sum(readiness) / len(readiness)) if readiness else 0,
    }


def _store(day: date, values: dict, department_id: int | None) -> int:
    session = context.session()
    now = context.now()
    for metric, value in values.items():
        session.add(MetricSnapshot(snapshot_date=day, metric=metric, department_id=department_id, category_id=None,
                                   value=float(value), created_at=now))
    return len(values)


def take(actor, day: date | None = None) -> int:
    """Store today's values for all departments together and for each department. Replaces today's earlier ones."""
    day = day or context.today()
    session = context.session()
    session.execute(delete(MetricSnapshot).where(MetricSnapshot.snapshot_date == day))
    n = _store(day, current_values(actor), None)
    for d in lk.by_id(Department).values():
        if d.archived_at is None:
            n += _store(day, current_values(actor, d.id), d.id)
    session.commit()
    return n


def has_today() -> bool:
    return context.session().scalar(select(MetricSnapshot.id).where(
        MetricSnapshot.snapshot_date == context.today()).limit(1)) is not None


def seed_history(actor, months: int = 12) -> int:
    """Demo only: month-end values for the past `months`, drifting plausibly toward today's real values."""
    today = context.today()
    n = take(actor, today)
    current = {None: current_values(actor)}
    for d in lk.by_id(Department).values():
        current[d.id] = current_values(actor, d.id)
    for back in range(1, months + 1):
        month_end = (today.replace(day=1) - timedelta(days=1))
        for _ in range(back - 1):
            month_end = month_end.replace(day=1) - timedelta(days=1)
        for department_id, values in current.items():
            rnd = random.Random(f"{back}:{department_id}")
            past = {}
            for metric, value in values.items():
                if metric.startswith("completion") or metric == "readiness_avg":
                    past[metric] = max(0, min(100, value - back * rnd.uniform(0.4, 1.6)))
                elif metric in ("assets_total", "assets_available", "assets_operational", "capabilities_total"):
                    past[metric] = max(0, round(value - back * rnd.uniform(0.1, 0.5)))
                else:
                    past[metric] = max(0, round(value + rnd.choice((-1, 0, 0, 1))))
            n += _store(month_end, past, department_id)
    context.session().commit()
    return n


def series(metric: str, department_id: int | None, since: date) -> list[dict]:
    rows = context.session().scalars(
        select(MetricSnapshot).where(MetricSnapshot.metric == metric, MetricSnapshot.snapshot_date >= since,
                                     MetricSnapshot.department_id.is_(None) if department_id is None
                                     else MetricSnapshot.department_id == department_id)
        .order_by(MetricSnapshot.snapshot_date))
    return [{"date": r.snapshot_date.isoformat(), "value": r.value} for r in rows]


def value_on_or_before(metric: str, department_id: int | None, day: date) -> float | None:
    row = context.session().scalar(
        select(MetricSnapshot).where(MetricSnapshot.metric == metric, MetricSnapshot.snapshot_date <= day,
                                     MetricSnapshot.department_id.is_(None) if department_id is None
                                     else MetricSnapshot.department_id == department_id)
        .order_by(MetricSnapshot.snapshot_date.desc()).limit(1))
    return row.value if row is not None else None
