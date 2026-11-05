"""Maintenance & technical readiness, AI capability levels, development potential and decision support.

AI level of a model: level N (1-5) is met when the model supports at least AI_LEVEL_CRITERION.min_supported
technologies and every required one; the model's level is the highest N met together with every lower level.
The trace says, per level, what is met and what is missing.

Decision support: factual panels only, each stating its basis and listing the records behind it. No unexplained
recommendations."""
from __future__ import annotations

from collections import Counter, defaultdict
from sqlalchemy import select

from ..exceptions import ValidationFailed
from ..models import (AiLevelCriterion, AiTechnology, Asset, CapabilityCategory, CapabilityModel, Department,
                      DevelopmentOpportunity, MaintenanceOrder, Milestone, ModelAiTech, Project, Risk, TestEvent)
from ..schemas.dto import record_meta, sid
from ..security.auth import ALL_DEPARTMENTS, PERM_EDIT_MAINTENANCE, PERM_EDIT_MODELS, department_scope
from . import (asset_service, audit_service, context, crud, lookup_service as lk, metrics_service, project_health,
               settings_service)

# ---------------------------------------------------------------- maintenance --------------------------------------


def _asset_scope(actor, query):
    scope = department_scope(actor)
    if scope is not ALL_DEPARTMENTS:
        query = query.where(Asset.department_id.in_(sorted(scope) or [-1]))
    return query


def maintenance_dto(m: MaintenanceOrder, asset: Asset) -> dict:
    today = context.today()
    terminal = m.status_code in ("COMPLETED", "CANCELLED")
    end = m.actual_end_date or (today if not terminal else m.expected_end_date)
    model = lk.by_id(CapabilityModel).get(asset.model_id)
    return {"id": sid(m.id), "code": m.code, "titleEn": m.title_en, "titleAr": m.title_ar, "type": m.maint_type,
            "asset": {"id": sid(asset.id), "code": asset.code, "status": asset.status_code},
            "model": lk.ref(model), "department": lk.ref_id(Department, asset.department_id),
            "status": m.status_code, "startDate": m.start_date.isoformat(),
            "expectedEndDate": m.expected_end_date.isoformat() if m.expected_end_date else None,
            "actualEndDate": m.actual_end_date.isoformat() if m.actual_end_date else None,
            "progressPct": m.progress_pct, "cost": m.cost, "partsShortage": bool(m.parts_shortage),
            "partsText": m.parts_text, "performedBy": m.performed_by,
            "overdue": not terminal and m.expected_end_date is not None and m.expected_end_date < today,
            "daysOverdue": max((today - m.expected_end_date).days, 0) if not terminal and m.expected_end_date else 0,
            "downtimeDays": max((end - m.start_date).days, 0) if end and m.start_date <= end else 0,
            **record_meta(m)}


def maintenance(actor, f: dict) -> dict:
    query = _asset_scope(actor, select(MaintenanceOrder, Asset).join(Asset, Asset.id == MaintenanceOrder.asset_id)
                         .where(MaintenanceOrder.archived_at.is_(None)))
    if f.get("department"):
        query = query.where(Asset.department_id.in_(f["department"]))
    if f.get("status"):
        query = query.where(MaintenanceOrder.status_code.in_(f["status"]))
    if f.get("type"):
        query = query.where(MaintenanceOrder.maint_type == f["type"])
    if f.get("asset"):
        query = query.where(MaintenanceOrder.asset_id.in_(f["asset"]))
    rows = context.session().execute(query.order_by(MaintenanceOrder.start_date.desc())).all()
    items = [maintenance_dto(m, a) for m, a in rows]
    open_items = [m for m in items if m["status"] not in ("COMPLETED", "CANCELLED")]
    done = [m for m in items if m["status"] == "COMPLETED"]
    # Readiness by department: averages over available assets (Settings: assets.available_statuses).
    available = set(settings_service.get("assets.available_statuses"))
    assets = list(context.session().scalars(_asset_scope(actor, select(Asset).where(Asset.archived_at.is_(None)))))
    by_dept = defaultdict(list)
    for a in assets:
        if a.status_code in available:
            by_dept[a.department_id].append(a)

    def avg(values):
        values = [v for v in values if v is not None]
        return round(sum(values) / len(values)) if values else None
    readiness = [{"department": lk.ref_id(Department, d), "assets": len(lst),
                  "operational": avg(a.readiness_operational for a in lst), "technical": avg(a.readiness_technical for a in lst),
                  "mission": avg(a.readiness_mission for a in lst), "maintenance": avg(a.readiness_maintenance for a in lst),
                  "overall": avg(asset_service.overall_readiness(a) for a in lst)}
                 for d, lst in sorted(by_dept.items())]
    by_category = defaultdict(Counter)
    for m in open_items + done:
        model = lk.by_id(CapabilityModel).get(int(m["model"]["id"])) if m["model"] else None
        cat = lk.by_id(CapabilityCategory).get(model.category_id) if model else None
        by_category[cat.code if cat else "-"][m["status"]] += 1
    not_ready_days = sum(m["downtimeDays"] for m in open_items)
    return {
        "items": items,
        "kpis": {"active": len(open_items), "overdue": sum(1 for m in open_items if m["overdue"]),
                 "partsShortage": sum(1 for m in open_items if m["partsShortage"]),
                 "awaitingParts": sum(1 for m in open_items if m["status"] == "AWAITING_PARTS"),
                 "completed": len(done),
                 "avgDuration": round(sum(m["downtimeDays"] for m in done) / len(done)) if done else None,
                 "downtimeDays": not_ready_days, "cost": sum(m["cost"] or 0 for m in items)},
        "readinessByDepartment": readiness,
        "byCategory": [{"category": k, **v} for k, v in sorted(by_category.items())],
    }


_MAINT_FIELDS = ("asset_id", "maint_type", "title_en", "title_ar", "status_code", "start_date", "expected_end_date",
                 "actual_end_date", "progress_pct", "cost", "parts_shortage", "parts_text", "performed_by")


def save_maintenance(actor, data, order_id: int | None = None) -> dict:
    session = context.session()
    if order_id is None:
        values = {k: getattr(data, k) for k in _MAINT_FIELDS}
        values["parts_shortage"] = 1 if values["parts_shortage"] else 0
        crud.check_unique_code(MaintenanceOrder, data.code)
        asset = crud.load(Asset, values["asset_id"], actor, "Asset")
        crud.check_status("MAINTENANCE", values["status_code"], "status")
        m = MaintenanceOrder(code=data.code, **values)
        crud.create(actor, m, PERM_EDIT_MAINTENANCE, asset.department_id)
    else:
        m = crud.load(MaintenanceOrder, order_id, actor, "Maintenance order", for_update=True,
                      department_of=lambda e: session.get(Asset, e.asset_id).department_id)
        changes = {k: v for k, v in data.changes().items() if k in _MAINT_FIELDS and k != "asset_id"}
        if "parts_shortage" in changes:
            changes["parts_shortage"] = 1 if changes["parts_shortage"] else 0
        crud.check_status("MAINTENANCE", changes.get("status_code"), "status", m.status_code)
        asset = session.get(Asset, m.asset_id)
        crud.update(actor, m, changes, PERM_EDIT_MAINTENANCE, data.version, data.reason,
                    department_ids=(asset.department_id,))
    return maintenance_dto(m, session.get(Asset, m.asset_id))


# ---------------------------------------------------------------- AI capability ------------------------------------


def _ai_context():
    session = context.session()
    techs = list(session.scalars(select(AiTechnology).where(AiTechnology.archived_at.is_(None))
                                 .order_by(AiTechnology.sort_order, AiTechnology.id)))
    criteria = list(session.scalars(select(AiLevelCriterion).order_by(AiLevelCriterion.ai_level)))
    supported = defaultdict(set)
    code_of = {t.id: t.code for t in techs}
    for model_id, tech_id in session.execute(select(ModelAiTech.model_id, ModelAiTech.technology_id)):
        if tech_id in code_of:
            supported[model_id].add(code_of[tech_id])
    return techs, criteria, supported


def ai_level(codes: set[str], criteria: list) -> tuple[int, list[dict]]:
    level = 0
    trace = []
    still = True
    for c in criteria:
        missing = [r for r in c.required if r not in codes]
        count_ok = len(codes) >= c.min_supported
        met = count_ok and not missing
        trace.append({"level": c.ai_level, "nameEn": c.name_en, "nameAr": c.name_ar, "met": met,
                      "minSupported": c.min_supported, "supported": len(codes), "missing": missing})
        if met and still:
            level = c.ai_level
        else:
            still = False
    return level, trace


def model_ai(actor, model_id: int) -> dict:
    model = crud.load(CapabilityModel, model_id, actor, "Model")
    techs, criteria, supported = _ai_context()
    codes = supported.get(model.id, set())
    level, trace = ai_level(codes, criteria)
    return {"model": lk.ref(model), "level": level, "trace": trace,
            "technologies": [{"code": t.code, "nameEn": t.name_en, "nameAr": t.name_ar, "supported": t.code in codes}
                             for t in techs]}


def ai_overview(actor) -> dict:
    techs, criteria, supported = _ai_context()
    models = [m for m in context.session().scalars(select(CapabilityModel).where(CapabilityModel.archived_at.is_(None))
                                                   .order_by(CapabilityModel.code))]
    rows = []
    level_of = {}
    for m in models:
        level, _ = ai_level(supported.get(m.id, set()), criteria)
        level_of[m.id] = level
        rows.append({"model": lk.ref(m), "category": lk.ref_id(CapabilityCategory, m.category_id), "level": level,
                     "supported": sorted(supported.get(m.id, set()))})
    # Averages weighted by assets in scope: department and category.
    assets = list(context.session().scalars(_asset_scope(actor, select(Asset).where(Asset.archived_at.is_(None)))))
    by_dept = defaultdict(list)
    by_cat = defaultdict(list)
    model_cat = {m.id: m.category_id for m in models}
    for a in assets:
        if a.model_id in level_of:
            by_dept[a.department_id].append(level_of[a.model_id])
            by_cat[model_cat[a.model_id]].append(level_of[a.model_id])
    opps = list(context.session().scalars(select(DevelopmentOpportunity).where(
        DevelopmentOpportunity.archived_at.is_(None), DevelopmentOpportunity.dev_type == "AI")))
    return {
        "technologies": [{"code": t.code, "nameEn": t.name_en, "nameAr": t.name_ar} for t in techs],
        "criteria": [{"level": c.ai_level, "nameEn": c.name_en, "nameAr": c.name_ar, "descriptionEn": c.description_en,
                      "descriptionAr": c.description_ar, "minSupported": c.min_supported, "required": c.required,
                      "version": c.version, "id": sid(c.id)} for c in criteria],
        "models": rows,
        "byDepartment": [{"department": lk.ref_id(Department, d), "average": round(sum(v) / len(v), 1)}
                         for d, v in sorted(by_dept.items())],
        "byCategory": [{"category": lk.ref_id(CapabilityCategory, c), "average": round(sum(v) / len(v), 1)}
                       for c, v in sorted(by_cat.items())],
        "levelCounts": dict(Counter(level_of.values())),
        "opportunities": [development_dto(o) for o in opps],
    }


def set_model_ai(actor, model_id: int, codes: list[str], reason: str | None) -> dict:
    model = crud.load(CapabilityModel, model_id, actor, "Model", for_update=True)
    from ..security.auth import require_edit
    require_edit(actor, PERM_EDIT_MODELS)
    session = context.session()
    techs = {t.code: t.id for t in session.scalars(select(AiTechnology))}
    unknown = [c for c in codes if c not in techs]
    if unknown:
        raise ValidationFailed.field("technologies", f"Unknown AI technology: {', '.join(unknown)}.")
    current = {code for code, tid in techs.items()
               if session.get(ModelAiTech, (model.id, tid)) is not None}
    wanted = set(codes)
    if current == wanted:
        return model_ai(actor, model_id)
    for code in current - wanted:
        session.delete(session.get(ModelAiTech, (model.id, techs[code])))
    for code in wanted - current:
        session.add(ModelAiTech(model_id=model.id, technology_id=techs[code], created_at=context.now()))
    before = {**audit_service.snapshot(model), "ai_technologies": ",".join(sorted(current)) or None}
    context.stamp_update(model, actor, context.now())
    session.flush()
    audit_service.record(actor, "UPDATE", model, before,
                         {**audit_service.snapshot(model), "ai_technologies": ",".join(sorted(wanted)) or None}, reason)
    session.commit()
    return model_ai(actor, model_id)


def update_ai_criterion(actor, level: int, data) -> dict:
    from ..security.auth import require_admin
    require_admin(actor)
    criterion = context.session().scalar(select(AiLevelCriterion).where(AiLevelCriterion.ai_level == level)
                                         .with_for_update(of=AiLevelCriterion.id))
    if criterion is None:
        from ..exceptions import NotFound
        raise NotFound(f"AI level {level} was not found.")
    changes = {k: v for k, v in data.changes().items()
               if k in ("name_en", "name_ar", "description_en", "description_ar", "min_supported")}
    if data.required is not None:
        techs = {t.code for t in context.session().scalars(select(AiTechnology))}
        unknown = [c for c in data.required if c not in techs]
        if unknown:
            raise ValidationFailed.field("required", f"Unknown AI technology: {', '.join(unknown)}.")
        changes["required_codes"] = ",".join(data.required) or None
    crud.update(actor, criterion, changes, "admin", data.version, data.reason, department_ids=(None,))
    return ai_overview(actor)["criteria"][level - 1]


# ---------------------------------------------------------------- development potential ----------------------------


def development_dto(o: DevelopmentOpportunity) -> dict:
    project = context.session().get(Project, o.project_id) if o.project_id else None
    return {"id": sid(o.id), "code": o.code, "model": lk.ref_id(CapabilityModel, o.model_id), "type": o.dev_type,
            "titleEn": o.title_en, "titleAr": o.title_ar, "benefitEn": o.benefit_en, "benefitAr": o.benefit_ar,
            "status": o.status_code, "complexity": o.complexity, "estimatedCost": o.estimated_cost,
            "durationMonths": o.duration_months, "priority": o.priority,
            "project": {"id": sid(project.id), "code": project.code} if project else None, **record_meta(o)}


def development(actor, f: dict) -> dict:
    query = select(DevelopmentOpportunity).where(DevelopmentOpportunity.archived_at.is_(None))
    if f.get("model"):
        query = query.where(DevelopmentOpportunity.model_id.in_(f["model"]))
    if f.get("status"):
        query = query.where(DevelopmentOpportunity.status_code.in_(f["status"]))
    if f.get("type"):
        query = query.where(DevelopmentOpportunity.dev_type == f["type"])
    rows = list(context.session().scalars(query.order_by(DevelopmentOpportunity.code)))
    return {"items": [development_dto(o) for o in rows],
            "byStatus": [{"status": k, "count": v} for k, v in Counter(o.status_code for o in rows).items()],
            "byType": [{"type": k, "count": v} for k, v in Counter(o.dev_type for o in rows).most_common()]}


_DEV_FIELDS = ("model_id", "dev_type", "title_en", "title_ar", "benefit_en", "benefit_ar", "status_code", "complexity",
               "estimated_cost", "duration_months", "priority", "project_id")


def save_development(actor, data, opp_id: int | None = None) -> dict:
    if opp_id is None:
        values = {k: getattr(data, k) for k in _DEV_FIELDS}
        crud.check_unique_code(DevelopmentOpportunity, data.code)
        crud.check_ref(CapabilityModel, values["model_id"], "modelId", "Model")
        if values["project_id"]:
            crud.check_ref(Project, values["project_id"], "projectId", "Project", True)
        crud.check_status("DEVELOPMENT", values["status_code"], "status")
        o = DevelopmentOpportunity(code=data.code, **values)
        crud.create(actor, o, PERM_EDIT_MODELS)
    else:
        o = crud.load(DevelopmentOpportunity, opp_id, actor, "Development opportunity", for_update=True)
        changes = {k: v for k, v in data.changes().items() if k in _DEV_FIELDS}
        if changes.get("project_id"):
            crud.check_ref(Project, changes["project_id"], "projectId", "Project", True)
        crud.check_status("DEVELOPMENT", changes.get("status_code"), "status", o.status_code)
        crud.update(actor, o, changes, PERM_EDIT_MODELS, data.version, data.reason, department_ids=(None,))
    return development_dto(o)


# ---------------------------------------------------------------- decision support ---------------------------------


def _panel(key: str, basis_en: str, basis_ar: str, items: list[dict]) -> dict:
    return {"key": key, "count": len(items), "basisEn": basis_en, "basisAr": basis_ar, "items": items}


def _item(text_en, text_ar, link, sub_en="", sub_ar="", tone="RED"):
    return {"textEn": text_en, "textAr": text_ar, "subEn": sub_en, "subAr": sub_ar, "link": link, "tone": tone}


_PRIORITY = {"CRITICAL": ("Critical", "حرجة"), "HIGH": ("High", "عالية"), "MEDIUM": ("Medium", "متوسطة"),
             "LOW": ("Low", "منخفضة")}


def _d(value) -> str:
    """Panel sub-lines are display text: dd/mm/yyyy with Western digits, as everywhere in the UI."""
    return value.strftime("%d/%m/%Y")


def decision_support(actor) -> dict:
    session = context.session()
    today = context.today()
    scope = department_scope(actor)

    def in_scope(dept_id):
        return scope is ALL_DEPARTMENTS or dept_id in scope

    panels = []
    reqs = metrics_service.requirement_metrics(actor)
    panels.append(_panel("criticalGaps", "Critical or high-priority requirements whose forecast still leaves a gap.",
                         "متطلبات حرجة أو عالية الأولوية تبقى فجوتها المتوقعة قائمة.",
                         [_item(f"{r['nameEn']}", f"{r['nameAr']}", f"/requirements/{r['id']}",
                                f"{r['department']['nameEn']} · current gap {r['gap']} · forecast gap {r['forecastGap']}",
                                f"{r['department']['nameAr']} · الفجوة الحالية {r['gap']} · المتوقعة {r['forecastGap']}")
                          for r in reqs if r["critical"]]))

    projects = [p for p in session.scalars(select(Project).where(Project.archived_at.is_(None))) if in_scope(p.department_id)]
    ctx = project_health.HealthContext([p.id for p in projects])
    healths = {p.id: project_health.health(p, ctx) for p in projects}
    at_risk = [p for p in projects if p.status_code not in ctx.terminal and healths[p.id]["overall"] == "RED"]
    panels.append(_panel("projectsAtRisk", "Active projects whose overall health is red, or forecast after target.",
                         "مشاريع نشطة سلامتها العامة حمراء أو موعدها المتوقع بعد المستهدف.",
                         [_item(f"{p.code} · {p.name_en}", f"{p.code} · {p.name_ar}", f"/projects/{p.id}",
                                f"Days late: {healths[p.id]['delayDays']}", f"أيام التأخير: {healths[p.id]['delayDays']}")
                          for p in sorted(at_risk, key=lambda p: -healths[p.id]["delayDays"])]))

    age_limit = settings_service.get("assets.replacement_age_years")
    assets = [a for a in session.scalars(select(Asset).where(Asset.archived_at.is_(None))) if in_scope(a.department_id)]
    models = lk.by_id(CapabilityModel)
    replace = [a for a in assets if a.status_code == "AWAITING_REPLACEMENT"
               or ((asset_service.age_years(a, today) or 0) > age_limit and a.status_code not in ("WRITTEN_OFF",))]
    panels.append(_panel("replacement", f"Assets awaiting replacement or older than {age_limit} years.",
                         f"أصول بانتظار الاستبدال أو يزيد عمرها عن {age_limit} سنة.",
                         [_item(f"{a.code} · {models[a.model_id].name_en}", f"{a.code} · {models[a.model_id].name_ar}",
                                f"/assets/{a.id}", f"Age {asset_service.age_years(a, today)} years",
                                f"العمر {asset_service.age_years(a, today)} سنة", "AMBER")
                          for a in sorted(replace, key=lambda a: -(asset_service.age_years(a, today) or 0))[:12]]))

    deliveries = []
    tests = []
    for m, p in session.execute(select(Milestone, Project).join(Project, Project.id == Milestone.project_id)
                                .where(Milestone.archived_at.is_(None), Milestone.status_code != "COMPLETED")):
        if not in_scope(p.department_id):
            continue
        end = m.forecast_end_date or m.planned_end_date
        if m.name_en == "Delivery" and 0 <= (end - today).days <= 180:
            deliveries.append(_item(f"{p.code} · {p.name_en}", f"{p.code} · {p.name_ar}", f"/projects/{p.id}?tab=milestones",
                                    _d(end), _d(end), "BLUE"))
    for e in session.scalars(select(TestEvent).where(TestEvent.archived_at.is_(None), TestEvent.status_code == "PLANNED")):
        if in_scope(e.department_id) and 0 <= (e.test_date - today).days <= 90:
            tests.append(_item(e.title_en, e.title_ar, "/testing", f"{_d(e.test_date)} · {e.test_type.lower()}",
                               _d(e.test_date), "BLUE"))
    open_maint = [m for m in session.scalars(select(MaintenanceOrder).where(MaintenanceOrder.archived_at.is_(None),
                                                                           MaintenanceOrder.status_code.notin_(("COMPLETED", "CANCELLED"))))]
    bottlenecks = []
    for m in open_maint:
        a = session.get(Asset, m.asset_id)
        if not in_scope(a.department_id):
            continue
        overdue = m.expected_end_date and m.expected_end_date < today
        if overdue or m.parts_shortage:
            bottlenecks.append(_item(f"{a.code} · {m.title_en}", f"{a.code} · {m.title_ar}", "/maintenance",
                                     (m.parts_text or "") + (" · overdue" if overdue else ""),
                                     (m.parts_text or "") + (" · متأخرة" if overdue else ""), "RED" if overdue else "AMBER"))
    panels.append(_panel("maintenance", "Open maintenance past its expected end, or waiting for spare parts.",
                         "أعمال صيانة مفتوحة تجاوزت موعدها المتوقع أو بانتظار قطع الغيار.", bottlenecks))
    panels.append(_panel("deliveries", "Delivery milestones not yet complete, due within 180 days.",
                         "مراحل التسليم غير المكتملة خلال 180 يوماً.", deliveries))
    panels.append(_panel("tests", "Planned tests within the next 90 days.", "اختبارات مخططة خلال 90 يوماً.", tests))

    by_dept = defaultdict(list)
    available = set(settings_service.get("assets.available_statuses"))
    for a in assets:
        if a.status_code in available and a.readiness_operational is not None:
            by_dept[a.department_id].append(a.readiness_operational)
    readiness = sorted(((d, round(sum(v) / len(v))) for d, v in by_dept.items()), key=lambda x: x[1])
    panels.append(_panel("lowReadiness", "Departments by average operational readiness of available assets, lowest first.",
                         "الإدارات حسب متوسط الجاهزية العملياتية للأصول المتوفرة، من الأقل.",
                         [_item(lk.by_id(Department)[d].name_en, lk.by_id(Department)[d].name_ar, "/maintenance",
                                f"{v}%", f"{v}%", "AMBER" if v < 80 else "GREEN") for d, v in readiness]))
    over = []
    budget_rule = settings_service.get("health.budget")
    for p in projects:
        if p.budget and p.status_code not in ctx.terminal:
            pct = round(100 * ((p.actual_spend or 0) + (p.committed or 0)) / p.budget)
            if pct - 100 > budget_rule["amber_pct"]:
                over.append(_item(f"{p.code} · {p.name_en}", f"{p.code} · {p.name_ar}", f"/projects/{p.id}", f"{pct}%", f"{pct}%"))
    panels.append(_panel("budget", "Active projects whose spend plus commitments exceed the budget.",
                         "مشاريع نشطة تتجاوز صرفها والتزاماتها الميزانية.", over))
    warranty = [a for a in assets if a.warranty_end_date and 0 <= (a.warranty_end_date - today).days <= 90]
    panels.append(_panel("warranty", "Asset warranties that end within 90 days.", "ضمانات أصول تنتهي خلال 90 يوماً.",
                         [_item(a.code, a.code, f"/assets/{a.id}", _d(a.warranty_end_date),
                                _d(a.warranty_end_date), "AMBER") for a in warranty]))
    opps = [o for o in session.scalars(select(DevelopmentOpportunity).where(
        DevelopmentOpportunity.archived_at.is_(None), DevelopmentOpportunity.project_id.is_(None),
        DevelopmentOpportunity.priority.in_(("CRITICAL", "HIGH")),
        DevelopmentOpportunity.status_code.in_(("PROPOSED", "POSSIBLE", "APPROVED", "UNDER_STUDY"))))]
    panels.append(_panel("opportunities", "High-priority development opportunities with no linked project.",
                         "فرص تطوير عالية الأولوية دون مشروع مرتبط.",
                         [_item(f"{o.code} · {o.title_en}", f"{o.code} · {o.title_ar}", "/development",
                                *_PRIORITY.get(o.priority, (o.priority, o.priority)), "BLUE") for o in opps]))
    risks = []
    for r, p in session.execute(select(Risk, Project).join(Project, Project.id == Risk.project_id)
                                .where(Risk.archived_at.is_(None), Risk.mitigation_due_date < today)):
        if in_scope(p.department_id) and r.status_code not in ctx.risk_terminal:
            risks.append(_item(f"{r.code} · {r.title_en}", f"{r.code} · {r.title_ar}", f"/projects/{p.id}?tab=risks",
                               f"{p.code} · due {_d(r.mitigation_due_date)}",
                               f"{p.code} · {_d(r.mitigation_due_date)}"))
    panels.append(_panel("overdueMitigations", "Open risks whose mitigation is past its due date.",
                         "مخاطر مفتوحة تجاوزت إجراءات معالجتها موعدها.", risks))
    return {"panels": panels, "asOf": today.isoformat()}

