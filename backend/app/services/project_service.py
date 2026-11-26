"""Projects: portfolio list and KPIs, project profile with its six health indicators, workflow path, milestones,
risks, issues; create / update / archive. Milestones, risks and issues follow the project's department scope."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import timedelta

from sqlalchemy import func, or_, select

from ..exceptions import ValidationFailed
from ..models import (CapabilityCategory, CapabilityModel, CapabilityRequirement, Contract, Department, Issue, Milestone,
                      Organization, Project, ProjectHealthNote, ProjectModel, ProjectRequirement, ProjectType, Risk,
                      WorkflowStage)
from ..repositories import common as repo
from ..schemas.dto import record_meta, sid
from ..security.auth import (ALL_DEPARTMENTS, PERM_EDIT_PROJECTS, PERM_EDIT_RISKS, department_scope, require_change,
                             require_department_access)
from . import audit_service, context, crud, lookup_service as lk, project_health

VIEWS = ("ACTIVE", "DELAYED", "DUE30", "DUE90", "ATTENTION", "COMPLETED")


def _scoped(actor, query, column=Project.department_id):
    scope = department_scope(actor)
    if scope is not ALL_DEPARTMENTS:
        query = query.where(column.in_(sorted(scope) or [-1]))
    return query


def _d(value):
    return value.isoformat() if value else None


def project_dto(p: Project, hl: dict, full: bool = False) -> dict:
    out = {
        "id": sid(p.id), "code": p.code, "nameEn": p.name_en, "nameAr": p.name_ar,
        "type": lk.ref_id(ProjectType, p.project_type_id), "department": lk.ref_id(Department, p.department_id),
        "category": lk.ref_id(CapabilityCategory, p.category_id), "status": p.status_code,
        "stage": lk.ref_id(WorkflowStage, p.stage_id), "managerName": p.manager_name,
        "budget": p.budget, "committed": p.committed, "actualSpend": p.actual_spend, "progressPct": p.progress_pct,
        "startDate": _d(p.start_date), "baselineEndDate": _d(p.baseline_end_date), "targetEndDate": _d(p.target_end_date),
        "forecastEndDate": _d(p.forecast_end_date), "actualEndDate": _d(p.actual_end_date),
        "health": hl["overall"], "delayDays": hl["delayDays"],
        **record_meta(p),
    }
    if full:
        out.update({
            "indicators": hl["indicators"], "supplier": lk.ref_id(Organization, p.supplier_id),
            "contract": (lambda c: {"id": sid(c.id), "code": c.code, "nameEn": c.title_en, "nameAr": c.title_ar}
                         if c else None)(context.session().get(Contract, p.contract_id) if p.contract_id else None),
            "nextActionEn": p.next_action_en, "nextActionAr": p.next_action_ar,
            "notesEn": p.notes_en, "notesAr": p.notes_ar,
            "requirements": [{"requirement": lk.ref_id(CapabilityRequirement, link.requirement_id), "quantity": link.quantity}
                             for link in p.requirement_links],
            "models": [{"model": lk.ref_id(CapabilityModel, link.model_id), "relation": link.relation} for link in p.model_links],
        })
    return out


def _filtered(actor, f: dict) -> tuple[list[tuple[Project, dict]], project_health.HealthContext]:
    query = _scoped(actor, select(Project))
    if not f.get("archived"):
        query = query.where(Project.archived_at.is_(None))
    if f.get("q"):
        pattern = repo.like_pattern(f["q"])
        query = query.where(or_(func.lower(Project.code).like(pattern, escape="\\"),
                                func.lower(Project.name_en).like(pattern, escape="\\"),
                                func.lower(Project.name_ar).like(pattern, escape="\\"),
                                func.lower(Project.manager_name).like(pattern, escape="\\")))
    for key, column in (("department", Project.department_id), ("category", Project.category_id),
                        ("type", Project.project_type_id)):
        if f.get(key):
            query = query.where(column.in_(f[key]))
    if f.get("status"):
        query = query.where(Project.status_code.in_(f["status"]))
    projects = list(context.session().scalars(query.order_by(Project.code)))
    ctx = project_health.HealthContext([p.id for p in projects])
    rows = [(p, project_health.health(p, ctx)) for p in projects]
    today = context.today()
    view = f.get("view")
    if view:
        def end(p):
            return p.forecast_end_date or p.target_end_date
        keep = {
            "ACTIVE": lambda p, hl: p.status_code not in ctx.terminal,
            "DELAYED": lambda p, hl: p.status_code not in ctx.terminal and hl["delayDays"] > 0,
            "DUE30": lambda p, hl: p.status_code not in ctx.terminal and end(p) and 0 <= (end(p) - today).days <= 30,
            "DUE90": lambda p, hl: p.status_code not in ctx.terminal and end(p) and 0 <= (end(p) - today).days <= 90,
            "ATTENTION": lambda p, hl: p.status_code not in ctx.terminal and hl["overall"] == "RED",
            "COMPLETED": lambda p, hl: p.status_code in ctx.terminal,
        }[view]
        rows = [(p, hl) for p, hl in rows if keep(p, hl)]
    if f.get("health"):
        rows = [(p, hl) for p, hl in rows if hl["overall"] in f["health"]]
    return rows, ctx


def portfolio(actor, f: dict) -> dict:
    rows, ctx = _filtered(actor, f)
    today = context.today()
    active = [(p, hl) for p, hl in rows if p.status_code not in ctx.terminal]

    def end(p):
        return p.forecast_end_date or p.target_end_date
    budget = sum(p.budget or 0 for p, _ in rows)
    spend = sum(p.actual_spend or 0 for p, _ in rows)
    open_risks = [r for p, _ in rows for r in ctx.risks.get(p.id, [])]
    kpis = {
        "total": len(rows), "completed": sum(1 for p, _ in rows if p.status_code == "COMPLETED"),
        "active": len(active), "delayed": sum(1 for _, hl in active if hl["delayDays"] > 0),
        "closed": sum(1 for p, _ in rows if p.status_code in ctx.terminal and p.status_code != "COMPLETED"),
        "development": sum(1 for p, _ in active if p.status_code == "DEVELOPMENT"),
        "testing": sum(1 for p, _ in active if p.status_code in ("TESTING", "FIELD_TRIALS", "EVALUATION")),
        "due30": sum(1 for p, _ in active if end(p) and 0 <= (end(p) - today).days <= 30),
        "due90": sum(1 for p, _ in active if end(p) and 0 <= (end(p) - today).days <= 90),
        "attention": sum(1 for _, hl in active if hl["overall"] == "RED"),
        "avgProgress": round(sum(p.progress_pct for p, _ in active) / len(active)) if active else 0,
        "budget": budget, "spend": spend, "spendPct": round(100 * spend / budget) if budget else None,
        "criticalRisks": sum(1 for r in open_risks if ctx.risk_level(r.probability * r.impact) == "CRITICAL"),
    }
    by = lambda key: Counter(key(p, hl) for p, hl in rows)  # noqa: E731
    by_dept_health = defaultdict(Counter)
    for p, hl in rows:
        by_dept_health[p.department_id][hl["overall"]] += 1
    quarters = Counter()
    for p, _ in active:
        if end(p):
            quarters[f"{end(p).year}-Q{(end(p).month - 1) // 3 + 1}"] += 1
    return {
        "kpis": kpis,
        "items": [project_dto(p, hl) for p, hl in rows],
        "charts": {
            "byDepartment": [{"department": lk.ref_id(Department, d), **{k: c.get(k, 0) for k in ("GREEN", "AMBER", "RED")}}
                             for d, c in sorted(by_dept_health.items())],
            "byStatus": [{"status": k, "count": v} for k, v in by(lambda p, hl: p.status_code).items()],
            "byStage": [{"stage": lk.ref_id(WorkflowStage, k), "count": v}
                        for k, v in by(lambda p, hl: p.stage_id).items() if k],
            "byCategory": [{"category": lk.ref_id(CapabilityCategory, k), "count": v}
                           for k, v in by(lambda p, hl: p.category_id).items()],
            "byHealth": {k: sum(1 for _, hl in rows if hl["overall"] == k) for k in ("GREEN", "AMBER", "RED")},
            "byQuarter": [{"quarter": q, "count": n} for q, n in sorted(quarters.items())],
        },
    }


def _load(actor, project_id: int, for_update: bool = False) -> Project:
    return crud.load(Project, project_id, actor, "Project", for_update=for_update)


def get_project(actor, project_id: int) -> dict:
    p = _load(actor, project_id)
    ctx = project_health.HealthContext([p.id])
    hl = project_health.health(p, ctx)
    out = project_dto(p, hl, full=True)
    session = context.session()
    stages = session.scalars(select(WorkflowStage).where(WorkflowStage.project_type_id == p.project_type_id,
                                                         WorkflowStage.archived_at.is_(None))
                             .order_by(WorkflowStage.sort_order)).all()
    current = next((s.sort_order for s in stages if s.id == p.stage_id), None)
    out["workflow"] = [{**lk.ref(s), "order": s.sort_order,
                        "state": "DONE" if current is not None and s.sort_order < current else
                        "CURRENT" if s.id == p.stage_id else "NEXT"} for s in stages]
    out["milestones"] = [milestone_dto(m, p) for m in session.scalars(
        select(Milestone).where(Milestone.project_id == p.id, Milestone.archived_at.is_(None))
        .order_by(Milestone.sort_order, Milestone.planned_start_date))]
    out["risks"] = [risk_dto(r, p, ctx) for r in session.scalars(
        select(Risk).where(Risk.project_id == p.id, Risk.archived_at.is_(None)).order_by(Risk.code))]
    out["issues"] = [issue_dto(i, p) for i in session.scalars(
        select(Issue).where(Issue.project_id == p.id, Issue.archived_at.is_(None)).order_by(Issue.code))]
    return out


# ---------------------------------------------------------------- milestones / risks / issues ----------------------


def _project_ref(p: Project) -> dict:
    return {"id": sid(p.id), "code": p.code, "nameEn": p.name_en, "nameAr": p.name_ar,
            "department": lk.ref_id(Department, p.department_id)}


def milestone_dto(m: Milestone, p: Project) -> dict:
    today = context.today()
    end = m.actual_end_date or m.forecast_end_date or m.planned_end_date
    slip = (end - m.planned_end_date).days if end else 0
    overdue = m.status_code != "COMPLETED" and m.actual_end_date is None and (m.forecast_end_date or m.planned_end_date) < today
    return {"id": sid(m.id), "nameEn": m.name_en, "nameAr": m.name_ar, "ownerName": m.owner_name,
            "project": _project_ref(p), "stage": lk.ref_id(WorkflowStage, m.stage_id),
            "plannedStartDate": _d(m.planned_start_date), "plannedEndDate": _d(m.planned_end_date),
            "actualEndDate": _d(m.actual_end_date), "forecastEndDate": _d(m.forecast_end_date),
            "status": m.status_code, "progressPct": m.progress_pct, "major": bool(m.is_major),
            "slipDays": slip, "overdue": overdue, "sortOrder": m.sort_order, **record_meta(m)}


def risk_dto(r: Risk, p: Project, ctx: project_health.HealthContext) -> dict:
    score = r.probability * r.impact
    today = context.today()
    return {"id": sid(r.id), "code": r.code, "titleEn": r.title_en, "titleAr": r.title_ar, "category": r.category,
            "project": _project_ref(p), "probability": r.probability, "impact": r.impact, "score": score,
            "level": ctx.risk_level(score), "ownerName": r.owner_name, "mitigationEn": r.mitigation_en,
            "mitigationAr": r.mitigation_ar, "mitigationDueDate": _d(r.mitigation_due_date), "status": r.status_code,
            "mitigationOverdue": bool(r.mitigation_due_date and r.mitigation_due_date < today
                                      and r.status_code not in ctx.risk_terminal),
            **record_meta(r)}


def issue_dto(i: Issue, p: Project) -> dict:
    today = context.today()
    terminal = project_health.terminal_codes("ISSUE")
    return {"id": sid(i.id), "code": i.code, "titleEn": i.title_en, "titleAr": i.title_ar, "severity": i.severity,
            "project": _project_ref(p), "ownerName": i.owner_name, "raisedDate": _d(i.raised_date),
            "targetDate": _d(i.target_date), "escalated": bool(i.is_escalated), "status": i.status_code,
            "resolutionEn": i.resolution_en, "resolutionAr": i.resolution_ar,
            "overdue": bool(i.target_date and i.target_date < today and i.status_code not in terminal),
            **record_meta(i)}


def _children(actor, model, f: dict):
    query = (select(model, Project).join(Project, Project.id == model.project_id)
             .where(model.archived_at.is_(None), Project.archived_at.is_(None)))
    query = _scoped(actor, query)
    if f.get("project"):
        query = query.where(model.project_id.in_(f["project"]))
    if f.get("department"):
        query = query.where(Project.department_id.in_(f["department"]))
    if f.get("status"):
        query = query.where(model.status_code.in_(f["status"]))
    return context.session().execute(query).all()


def list_milestones(actor, f: dict) -> dict:
    rows = _children(actor, Milestone, f)
    items = [milestone_dto(m, p) for m, p in sorted(rows, key=lambda mp: (mp[0].planned_end_date, mp[1].code))]
    if f.get("majorOnly"):
        items = [m for m in items if m["major"]]
    today = context.today()
    return {"items": items, "kpis": {
        "total": len(items), "completed": sum(1 for m in items if m["status"] == "COMPLETED"),
        "inProgress": sum(1 for m in items if m["status"] in ("IN_PROGRESS", "DELAYED")),
        "overdue": sum(1 for m in items if m["overdue"]),
        "next90": sum(1 for m in items if m["status"] != "COMPLETED" and m["plannedEndDate"]
                      and 0 <= (context.today().fromisoformat(m["plannedEndDate"]) - today).days <= 90)}}


def list_risks(actor, f: dict) -> dict:
    rows = _children(actor, Risk, f)
    ctx = project_health.HealthContext(list({p.id for _, p in rows}))
    items = sorted((risk_dto(r, p, ctx) for r, p in rows), key=lambda r: (-r["score"], r["code"]))
    if f.get("level"):
        items = [r for r in items if r["level"] in f["level"]]
    open_items = [r for r in items if r["status"] not in ctx.risk_terminal]
    matrix = Counter((r["probability"], r["impact"]) for r in open_items)
    return {"items": items, "matrix": [{"probability": pr, "impact": im, "count": n} for (pr, im), n in matrix.items()],
            "kpis": {"open": len(open_items),
                     "critical": sum(1 for r in open_items if r["level"] == "CRITICAL"),
                     "high": sum(1 for r in open_items if r["level"] == "HIGH"),
                     "overdueMitigations": sum(1 for r in open_items if r["mitigationOverdue"]),
                     "mitigating": sum(1 for r in open_items if r["status"] == "MITIGATING"),
                     "closed": sum(1 for r in items if r["status"] in ctx.risk_terminal)},
            "byCategory": [{"category": c, "count": n} for c, n in Counter(r["category"] for r in open_items).most_common()],
            "thresholds": ctx.risk}


def list_issues(actor, f: dict) -> dict:
    rows = _children(actor, Issue, f)
    terminal = project_health.terminal_codes("ISSUE")
    items = sorted((issue_dto(i, p) for i, p in rows), key=lambda i: (i["status"] in terminal, i["code"]))
    if f.get("severity"):
        items = [i for i in items if i["severity"] in f["severity"]]
    open_items = [i for i in items if i["status"] not in terminal]
    return {"items": items, "kpis": {
        "open": len(open_items), "critical": sum(1 for i in open_items if i["severity"] == "CRITICAL"),
        "escalated": sum(1 for i in open_items if i["escalated"]),
        "overdue": sum(1 for i in open_items if i["overdue"]),
        "resolved": sum(1 for i in items if i["status"] in terminal)}}


# ---------------------------------------------------------------- writes -------------------------------------------

_PROJECT_FIELDS = ("name_en", "name_ar", "project_type_id", "department_id", "category_id", "status_code", "stage_id",
                   "manager_name", "supplier_id", "contract_id", "budget", "committed", "actual_spend", "progress_pct",
                   "start_date", "baseline_end_date", "target_end_date", "forecast_end_date", "actual_end_date",
                   "next_action_en", "next_action_ar", "notes_en", "notes_ar")


def _validate_project(values: dict, current: Project | None = None) -> None:
    def same(field):
        return current is not None and getattr(current, field) == values.get(field)
    if "project_type_id" in values:
        crud.check_ref(ProjectType, values["project_type_id"], "projectTypeId", "Project type", same("project_type_id"))
    if "department_id" in values:
        crud.check_ref(Department, values["department_id"], "departmentId", "Department", same("department_id"))
    if "category_id" in values:
        crud.check_ref(CapabilityCategory, values["category_id"], "categoryId", "Category", same("category_id"))
    if values.get("supplier_id") is not None:
        crud.check_ref(Organization, values["supplier_id"], "supplierId", "Organization", same("supplier_id"))
    if values.get("contract_id") is not None:
        crud.check_ref(Contract, values["contract_id"], "contractId", "Contract", True)
    if "status_code" in values:
        crud.check_status("PROJECT", values["status_code"], "status", current.status_code if current else None)
    if values.get("stage_id") is not None:
        stage = crud.check_ref(WorkflowStage, values["stage_id"], "stageId", "Stage", same("stage_id"))
        type_id = values.get("project_type_id", current.project_type_id if current else None)
        if stage.project_type_id != type_id:
            raise ValidationFailed.field("stageId", "The stage is not part of this project type's workflow.")
    start = values.get("start_date", current.start_date if current else None)
    target = values.get("target_end_date", current.target_end_date if current else None)
    if start and target and target < start:
        raise ValidationFailed.field("targetEndDate", "The target end date is before the start date.")


def _set_links(p: Project, requirements: list | None, models: list | None) -> None:
    now = context.now()
    if requirements is not None:
        wanted = {r.requirement_id: r.quantity for r in requirements}
        for req_id in wanted:
            crud.check_ref(CapabilityRequirement, req_id, "requirements", "Requirement",
                           any(link.requirement_id == req_id for link in p.requirement_links))
        p.requirement_links[:] = [link for link in p.requirement_links if link.requirement_id in wanted]
        for link in p.requirement_links:
            link.quantity = wanted[link.requirement_id]
        have = {link.requirement_id for link in p.requirement_links}
        for req_id, qty in wanted.items():
            if req_id not in have:
                p.requirement_links.append(ProjectRequirement(requirement_id=req_id, quantity=qty, created_at=now))
    if models is not None:
        wanted = {m.model_id: m.relation for m in models}
        for model_id in wanted:
            crud.check_ref(CapabilityModel, model_id, "models", "Model",
                           any(link.model_id == model_id for link in p.model_links))
        p.model_links[:] = [link for link in p.model_links if link.model_id in wanted]
        for link in p.model_links:
            link.relation = wanted[link.model_id]
        have = {link.model_id for link in p.model_links}
        for model_id, relation in wanted.items():
            if model_id not in have:
                p.model_links.append(ProjectModel(model_id=model_id, relation=relation, created_at=now))


def _links_snapshot(p: Project) -> dict:
    return {"requirements_text": ",".join(f"{l.requirement_id}:{l.quantity}" for l in sorted(
                p.requirement_links, key=lambda l: l.requirement_id)) or None,
            "models_text": ",".join(f"{l.model_id}:{l.relation}" for l in sorted(
                p.model_links, key=lambda l: l.model_id)) or None}


def create_project(actor, data) -> dict:
    values = {k: getattr(data, k) for k in _PROJECT_FIELDS}
    crud.check_unique_code(Project, data.code)
    _validate_project(values)
    if values["stage_id"] is None:
        first = context.session().scalar(select(WorkflowStage).where(
            WorkflowStage.project_type_id == values["project_type_id"], WorkflowStage.archived_at.is_(None))
            .order_by(WorkflowStage.sort_order).limit(1))
        values["stage_id"] = first.id if first else None
    if values["baseline_end_date"] is None:
        values["baseline_end_date"] = values["target_end_date"]
    p = Project(code=data.code, **values)
    _set_links(p, data.requirements, data.models)
    crud.create(actor, p, PERM_EDIT_PROJECTS, data.department_id)
    return get_project(actor, p.id)


def update_project(actor, project_id: int, data) -> dict:
    p = _load(actor, project_id, for_update=True)
    changes = {k: v for k, v in data.changes().items() if k in _PROJECT_FIELDS}
    _validate_project({**changes}, p)
    before_links = _links_snapshot(p)
    _set_links(p, data.requirements, data.models)
    changed = crud.update(actor, p, changes, PERM_EDIT_PROJECTS, data.version, data.reason,
                          department_ids=(p.department_id, changes.get("department_id", p.department_id)),
                          commit=False, extra_snapshot=lambda: _links_snapshot(p))
    if not changed and _links_snapshot(p) != before_links:
        context.stamp_update(p, actor, context.now())
        context.session().flush()
        audit_service.record(actor, "UPDATE", p, {**audit_service.snapshot(p), **before_links},
                             {**audit_service.snapshot(p), **_links_snapshot(p)}, data.reason)
    context.session().commit()
    return get_project(actor, p.id)


def set_health_note(actor, project_id: int, dimension: str, rag: str, reason_en, reason_ar, reason) -> dict:
    p = _load(actor, project_id, for_update=True)
    # A note sets how an existing project is judged: a change, also when it is the first note on that indicator.
    require_change(actor, PERM_EDIT_PROJECTS, p.department_id)
    session = context.session()
    note = session.scalar(select(ProjectHealthNote).where(ProjectHealthNote.project_id == p.id,
                                                          ProjectHealthNote.dimension == dimension))
    if note is None:
        note = ProjectHealthNote(project_id=p.id, dimension=dimension, rag=rag, reason_en=reason_en, reason_ar=reason_ar)
        crud.create(actor, note, PERM_EDIT_PROJECTS, p.department_id, reason)
    else:
        crud.update(actor, note, {"rag": rag, "reason_en": reason_en, "reason_ar": reason_ar}, PERM_EDIT_PROJECTS,
                    None, reason, department_ids=(p.department_id,))
    return get_project(actor, p.id)


def archive_project(actor, project_id: int, archived: bool, version, reason) -> dict:
    p = _load(actor, project_id, for_update=True)
    crud.set_archived(actor, p, archived, PERM_EDIT_PROJECTS, version, reason)
    return get_project(actor, p.id)


def _child(actor, model, entity_id: int, what: str, for_update=False):
    entity = repo.get(context.session(), model, entity_id, for_update=for_update)
    if entity is None:
        from ..exceptions import NotFound
        raise NotFound(f"{what} {entity_id} was not found.")
    project = context.session().get(Project, entity.project_id)
    require_department_access(actor, project.department_id, f"{what} {entity_id} was not found.")
    return entity, project


def _check_project(actor, project_id: int) -> Project:
    project = crud.load(Project, project_id, actor, "Project")
    if project.archived_at is not None:
        raise ValidationFailed.field("projectId", "The project is archived.")
    return project


_MILESTONE_FIELDS = ("name_en", "name_ar", "stage_id", "owner_name", "planned_start_date", "planned_end_date",
                     "actual_end_date", "forecast_end_date", "status_code", "progress_pct", "is_major", "sort_order")


def save_milestone(actor, data, milestone_id: int | None = None) -> dict:
    if milestone_id is None:
        p = _check_project(actor, data.project_id)
        values = {k: getattr(data, k) for k in _MILESTONE_FIELDS}
        values["is_major"] = 1 if values["is_major"] else 0
        crud.check_status("MILESTONE", values["status_code"], "status")
        if values["planned_end_date"] < values["planned_start_date"]:
            raise ValidationFailed.field("plannedEndDate", "The planned end is before the planned start.")
        m = Milestone(project_id=p.id, **values)
        crud.create(actor, m, PERM_EDIT_PROJECTS, p.department_id)
    else:
        m, p = _child(actor, Milestone, milestone_id, "Milestone", for_update=True)
        changes = {k: v for k, v in data.changes().items() if k in _MILESTONE_FIELDS}
        if "is_major" in changes:
            changes["is_major"] = 1 if changes["is_major"] else 0
        crud.check_status("MILESTONE", changes.get("status_code"), "status", m.status_code)
        start = changes.get("planned_start_date", m.planned_start_date)
        end = changes.get("planned_end_date", m.planned_end_date)
        if end < start:
            raise ValidationFailed.field("plannedEndDate", "The planned end is before the planned start.")
        crud.update(actor, m, changes, PERM_EDIT_PROJECTS, data.version, data.reason, department_ids=(p.department_id,))
    return milestone_dto(m, p)


_RISK_FIELDS = ("title_en", "title_ar", "category", "probability", "impact", "owner_name", "mitigation_en",
                "mitigation_ar", "mitigation_due_date", "status_code")


def save_risk(actor, data, risk_id: int | None = None) -> dict:
    if risk_id is None:
        p = _check_project(actor, data.project_id)
        crud.check_unique_code(Risk, data.code)
        crud.check_status("RISK", data.status_code, "status")
        r = Risk(code=data.code, project_id=p.id, **{k: getattr(data, k) for k in _RISK_FIELDS})
        crud.create(actor, r, PERM_EDIT_RISKS, p.department_id)
    else:
        r, p = _child(actor, Risk, risk_id, "Risk", for_update=True)
        changes = {k: v for k, v in data.changes().items() if k in _RISK_FIELDS}
        crud.check_status("RISK", changes.get("status_code"), "status", r.status_code)
        crud.update(actor, r, changes, PERM_EDIT_RISKS, data.version, data.reason, department_ids=(p.department_id,))
    return risk_dto(r, p, project_health.HealthContext([p.id]))


_ISSUE_FIELDS = ("title_en", "title_ar", "severity", "owner_name", "raised_date", "target_date", "is_escalated",
                 "status_code", "resolution_en", "resolution_ar")


def save_issue(actor, data, issue_id: int | None = None) -> dict:
    if issue_id is None:
        p = _check_project(actor, data.project_id)
        crud.check_unique_code(Issue, data.code)
        crud.check_status("ISSUE", data.status_code, "status")
        values = {k: getattr(data, k) for k in _ISSUE_FIELDS}
        values["is_escalated"] = 1 if values["is_escalated"] else 0
        values["raised_date"] = values["raised_date"] or context.today()
        i = Issue(code=data.code, project_id=p.id, **values)
        crud.create(actor, i, PERM_EDIT_RISKS, p.department_id)
    else:
        i, p = _child(actor, Issue, issue_id, "Issue", for_update=True)
        changes = {k: v for k, v in data.changes().items() if k in _ISSUE_FIELDS}
        if "is_escalated" in changes:
            changes["is_escalated"] = 1 if changes["is_escalated"] else 0
        crud.check_status("ISSUE", changes.get("status_code"), "status", i.status_code)
        crud.update(actor, i, changes, PERM_EDIT_RISKS, data.version, data.reason, department_ids=(p.department_id,))
    return issue_dto(i, p)


def next_code(model, prefix: str) -> str:
    codes = context.session().scalars(select(model.code).where(model.code.like(f"{prefix}-%"))).all()
    numbers = [int(c.split("-")[-1]) for c in codes if c.split("-")[-1].isdigit()]
    return f"{prefix}-{(max(numbers) + 1 if numbers else 1):03d}"


def timeline(actor, f: dict) -> dict:
    """Strategic timeline: every project with its bar (start -> target), forecast slip, major milestones and
    deliveries, within the chosen window."""
    rows, ctx = _filtered(actor, f)
    session = context.session()
    ids = [p.id for p, _ in rows]
    milestones = defaultdict(list)
    if ids:
        for m in session.scalars(select(Milestone).where(Milestone.project_id.in_(ids), Milestone.archived_at.is_(None),
                                                         Milestone.is_major == 1)):
            milestones[m.project_id].append(m)
    items = []
    for p, hl in rows:
        dto = project_dto(p, hl)
        p_obj = p
        dto["milestones"] = [milestone_dto(m, p_obj) for m in sorted(milestones[p.id], key=lambda m: m.planned_end_date)]
        items.append(dto)
    today = context.today()
    return {"today": today.isoformat(), "items": items,
            "window": {"from": (today - timedelta(days=365)).isoformat(), "to": (today + timedelta(days=365 * 3)).isoformat()}}
