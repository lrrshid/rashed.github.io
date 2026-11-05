"""Seeds the reference lists (every profile, through `seed_reference`) and the brochure-shaped demo world (demo profile
only). Every record is written with its created/updated stamps and an audit row, like a change made in the app.
Deterministic: the same day gives the same data."""
from __future__ import annotations

import json
import random
from datetime import date, timedelta

from sqlalchemy import func, select

from ..models import (Asset, AssetStatusHistory, AppRole, AppUser, CapabilityCategory, CapabilityModel,
                      CapabilityRequirement, Contract, Department, Issue, Milestone, Organization, Project,
                      ProjectHealthNote, ProjectModel, ProjectRequirement, ProjectType, RequirementModel, Risk,
                      RolePermission, Site, SpecField, StatusDef, WorkflowStage)
from ..security.mock_credentials import MOCK_PASSWORD
from ..services import audit_service, context, user_service
from . import fixture_data as fx
from . import reference_data as ref


class SeedRefused(RuntimeError):
    pass


def _guard_profile() -> None:
    if context.settings().profile == "oracle":
        raise SeedRefused("The demo data is never written to Oracle. Use `flask seed-reference --actor <admin>` there.")


def _add(actor, entity):
    session = context.session()
    context.stamp_create(entity, actor, context.now())
    session.add(entity)
    session.flush()
    audit_service.record(actor, "CREATE", entity, None, audit_service.snapshot(entity), "Demo data")
    return entity


# ---------------------------------------------------------------- reference data ----------------------------------


def seed_roles() -> int:
    """Roles and their permissions (no actor needed: they exist before any user)."""
    session = context.session()
    have = {r.code for r in session.scalars(select(AppRole))}
    now = context.now()
    added = 0
    for order, (code, en, ar, scope, permissions) in enumerate(ref.ROLES):
        if code in have:
            continue
        role = AppRole(code=code, name_en=en, name_ar=ar, scope=scope, is_system=1 if code == "SYS_ADMIN" else 0,
                       sort_order=order, created_at=now, updated_at=now)
        role.permission_links = [RolePermission(permission=p, created_at=now) for p in permissions]
        session.add(role)
        added += 1
    session.flush()
    return added


def seed_reference(actor) -> dict:
    """Lists every installation starts with. Only adds what is missing (by code)."""
    session = context.session()
    counts = {}

    def missing(model, code, **where):
        query = select(model.id).where(model.code == code)
        for k, v in where.items():
            query = query.where(getattr(model, k) == v)
        return session.scalar(query) is None

    n = 0
    for order, (code, en, ar) in enumerate(ref.DEPARTMENTS):
        if missing(Department, code):
            _add(actor, Department(code=code, name_en=en, name_ar=ar, sort_order=order)); n += 1
    counts["departments"] = n
    n = 0
    for order, (code, en, ar) in enumerate(ref.CATEGORIES):
        if missing(CapabilityCategory, code):
            _add(actor, CapabilityCategory(code=code, name_en=en, name_ar=ar, sort_order=order)); n += 1
    counts["categories"] = n
    n = 0
    for domain, rows in ref.STATUSES.items():
        for order, (code, en, ar, color, terminal) in enumerate(rows):
            if missing(StatusDef, code, domain=domain):
                _add(actor, StatusDef(domain=domain, code=code, name_en=en, name_ar=ar, color=color,
                                      is_terminal=terminal, sort_order=order)); n += 1
    counts["statuses"] = n
    n = 0
    for order, (code, en, ar, color, stages) in enumerate(ref.PROJECT_TYPES):
        if not missing(ProjectType, code):
            continue
        ptype = _add(actor, ProjectType(code=code, name_en=en, name_ar=ar, color=color, sort_order=order))
        for i, (s_en, s_ar) in enumerate(stages, start=1):
            _add(actor, WorkflowStage(project_type_id=ptype.id, name_en=s_en, name_ar=s_ar, sort_order=i))
        n += 1
    counts["projectTypes"] = n
    n = 0
    categories = {c.code: c.id for c in session.scalars(select(CapabilityCategory))}
    for cat_code, fields in ref.SPEC_FIELDS.items():
        if cat_code not in categories:
            continue
        for order, (section, code, en, ar, unit, dtype) in enumerate(fields):
            if missing(SpecField, code, category_id=categories[cat_code]):
                _add(actor, SpecField(category_id=categories[cat_code], section=section, code=code, name_en=en,
                                      name_ar=ar, unit=unit, data_type=dtype, sort_order=order)); n += 1
    counts["specFields"] = n
    from ..models import AiLevelCriterion, AiTechnology
    n = 0
    for order, (code, en, ar) in enumerate(ref.AI_TECHNOLOGIES):
        if missing(AiTechnology, code):
            _add(actor, AiTechnology(code=code, name_en=en, name_ar=ar, sort_order=order)); n += 1
    counts["aiTechnologies"] = n
    n = 0
    have_levels = set(session.scalars(select(AiLevelCriterion.ai_level)))
    for level, en, ar, d_en, d_ar, minimum, required in ref.AI_LEVELS:
        if level not in have_levels:
            _add(actor, AiLevelCriterion(ai_level=level, name_en=en, name_ar=ar, description_en=d_en,
                                         description_ar=d_ar, min_supported=minimum, required_codes=required or None))
            n += 1
    counts["aiLevels"] = n
    from ..services import alert_service
    counts["alertRules"] = alert_service.ensure_rules(actor)
    session.commit()
    return counts


# ---------------------------------------------------------------- demo world --------------------------------------


def _readiness(status: str, rnd: random.Random) -> tuple:
    bands = {
        "READY": (85, 98), "READY_LIMITED": (68, 80), "TEMP_NOT_READY": (35, 60), "UNDER_MAINTENANCE": (0, 30),
        "NOT_READY": (0, 15), "AWAITING_REPLACEMENT": (0, 10), "WRITTEN_OFF": (0, 0),
    }
    if status not in bands:
        return None, None, None, None
    low, high = bands[status]
    op = rnd.randint(low, high)
    return (op, min(100, max(0, op + rnd.randint(-6, 8))), min(100, max(0, op + rnd.randint(-10, 4))),
            min(100, max(0, op + rnd.randint(-3, 10))))


def seed_demo() -> dict:
    _guard_profile()
    session = context.session()
    seed_roles()
    admin_name, admin_display, _, _ = fx.MOCK_USERS[0]
    admin = user_service.create_user(admin_name, admin_display, "SYS_ADMIN", MOCK_PASSWORD,
                                     note="Demo account (mock password)")
    seed_reference(admin)
    for username, name, role, departments in fx.MOCK_USERS[1:]:
        dept_ids = [session.scalar(select(Department.id).where(Department.code == c)) for c in departments]
        user_service.create_user(username, name, role, MOCK_PASSWORD, actor=admin, department_ids=dept_ids,
                                 note="Demo account (mock password)")

    today = context.today()

    def day(offset: int | None) -> date | None:
        return None if offset is None else today + timedelta(days=offset)

    dept = {d.code: d.id for d in session.scalars(select(Department))}
    cat = {c.code: c.id for c in session.scalars(select(CapabilityCategory))}
    sites = {}
    for order, (code, en, ar) in enumerate(fx.SITES):
        sites[code] = _add(admin, Site(code=code, name_en=en, name_ar=ar, sort_order=order)).id
    orgs = {}
    for order, (code, en, ar, kind, c_en, c_ar) in enumerate(fx.ORGANIZATIONS):
        orgs[code] = _add(admin, Organization(code=code, name_en=en, name_ar=ar, kind=kind, country_en=c_en,
                                              country_ar=c_ar, sort_order=order)).id
    contracts = {}
    for code, en, ar, supplier, value, start, end in fx.CONTRACTS:
        contracts[code] = _add(admin, Contract(code=code, title_en=en, title_ar=ar, supplier_id=orgs[supplier],
                                               contract_value=value, start_date=day(start), end_date=day(end))).id
    models = {}
    for code, en, ar, category, mfr, role_en, role_ar, cost, specs in fx.MODELS:
        models[code] = _add(admin, CapabilityModel(
            code=code, name_en=en, name_ar=ar, category_id=cat[category], manufacturer_id=orgs[mfr], role_en=role_en,
            role_ar=role_ar, unit_cost=cost, specs_json=json.dumps(specs, ensure_ascii=False, sort_keys=True))).id
    model_category = {code: category for code, _, _, category, *_ in fx.MODELS}

    requirements = {}
    counters: dict[str, int] = {}
    serial_no = 1000
    for code, en, ar, d, c, required, priority, model_codes, letters in fx.REQUIREMENTS:
        req = CapabilityRequirement(code=code, name_en=en, name_ar=ar, department_id=dept[d], category_id=cat[c],
                                    required_qty=required, priority=priority, target_date=day(365))
        req.model_links = [RequirementModel(model_id=models[m], created_at=context.now()) for m in model_codes]
        requirements[code] = _add(admin, req).id
        for i, letter in enumerate(letters):
            model_code = model_codes[i % len(model_codes)]
            category = model_category[model_code]
            counters[category] = counters.get(category, 0) + 1
            asset_code = f"{category}-{counters[category]:03d}"
            rnd = random.Random(asset_code)
            status = fx.STATUS_LETTERS[letter]
            pipeline = status in ("UNDER_ACQUISITION", "UNDER_DEVELOPMENT", "UNDER_TEST")
            op, tech, mission, maint = _readiness(status, rnd)
            acquired = None if pipeline else day(-rnd.randint(150, 2100))
            serial_no += 1
            site_codes = fx.DEPARTMENT_SITES[d]
            asset = Asset(
                code=asset_code,
                serial_number=None if pipeline else f"SN{serial_no % 97:02d}-{acquired.year}-{rnd.randint(1000, 9999)}",
                model_id=models[model_code], department_id=dept[d],
                site_id=sites["TER"] if status == "UNDER_TEST" else sites[site_codes[i % len(site_codes)]],
                status_code=status, readiness_operational=op, readiness_technical=tech, readiness_mission=mission,
                readiness_maintenance=maint, acquisition_date=acquired,
                expected_delivery_date=day(rnd.randint(30, 400)) if pipeline else None,
                acquisition_method="DEVELOPMENT" if status == "UNDER_DEVELOPMENT" else "DIRECT_CONTRACT",
                contract_id=contracts.get(fx.MODEL_CONTRACTS.get(model_code)) if not pipeline else None,
                warranty_end_date=(acquired + timedelta(days=365 * rnd.choice((2, 3, 5)))) if acquired else None,
                unit_value=next(m[7] for m in fx.MODELS if m[0] == model_code),
                service_life_years=rnd.choice((8, 10, 12)),
                operating_hours=None if pipeline else rnd.randint(40, 1400),
                responsible_en=f"{fx.PEOPLE[rnd.randint(0, len(fx.PEOPLE) - 1)]} / Operations section",
                responsible_ar="قسم العمليات")
            _add(admin, asset)
            # A short status history: acquired ready, then today's status.
            if acquired:
                session.add(AssetStatusHistory(asset_id=asset.id, status_code="READY", readiness=95,
                                               changed_at=context.now() - timedelta(days=(today - acquired).days),
                                               changed_by=admin.id, note="Entered service"))
            session.add(AssetStatusHistory(asset_id=asset.id, status_code=status, readiness=op,
                                           changed_at=context.now() - timedelta(days=rnd.randint(1, 120)),
                                           changed_by=admin.id, note=None))

    types = {t.code: t for t in session.scalars(select(ProjectType))}
    stages_by_type = {}
    for stage in session.scalars(select(WorkflowStage).order_by(WorkflowStage.project_type_id, WorkflowStage.sort_order)):
        stages_by_type.setdefault(stage.project_type_id, []).append(stage)
    projects = {}
    milestone_count = 0
    for (code, en, ar, ptype, d, c, status, mgr, start, target, forecast, progress, budget, committed, spend,
         supplier, contract, req_links, model_links, next_en, next_ar) in fx.PROJECTS:
        stages = stages_by_type[types[ptype].id]
        current_index = min(len(stages) - 1, int(len(stages) * progress / 100))
        project = Project(
            code=code, name_en=en, name_ar=ar, project_type_id=types[ptype].id, department_id=dept[d],
            category_id=cat[c], status_code=status, stage_id=stages[current_index].id, manager_name=fx.PEOPLE[mgr],
            supplier_id=orgs.get(supplier), contract_id=contracts.get(contract), budget=budget, committed=committed,
            actual_spend=spend, progress_pct=progress, start_date=day(start), baseline_end_date=day(target),
            target_end_date=day(target), forecast_end_date=day(forecast),
            actual_end_date=day(forecast) if status == "COMPLETED" else None,
            next_action_en=next_en, next_action_ar=next_ar)
        project.requirement_links = [ProjectRequirement(requirement_id=requirements[r], quantity=q,
                                                        created_at=context.now()) for r, q in req_links]
        project.model_links = [ProjectModel(model_id=models[m], relation=rel, created_at=context.now())
                               for m, rel in model_links]
        _add(admin, project)
        projects[code] = project.id
        # Milestones: one per workflow stage, spread between start and target; the slip moves the open ones.
        slip = forecast - target
        span = max(target - start, len(stages))
        step = span / len(stages)
        for i, stage in enumerate(stages):
            p_start = start + round(i * step)
            p_end = start + round((i + 1) * step) - 1
            if i < current_index or status == "COMPLETED":
                ms_status, ms_progress = "COMPLETED", 100
                actual = p_end + (random.Random(f"{code}{i}").randint(0, max(1, slip // 2)) if slip > 0 else 0)
                actual = min(actual, -1) if status != "COMPLETED" else actual
                ms_forecast = actual
            elif i == current_index:
                ms_status = "DELAYED" if slip > 0 else "IN_PROGRESS"
                ms_progress = min(95, max(5, round((progress / 100 * len(stages) - i) * 100)))
                actual, ms_forecast = None, p_end + max(slip, 0)
            else:
                ms_status, ms_progress, actual, ms_forecast = "NOT_STARTED", 0, None, p_end + max(slip, 0)
            _add(admin, Milestone(
                project_id=project.id, stage_id=stage.id, name_en=stage.name_en, name_ar=stage.name_ar,
                owner_name=fx.PEOPLE[mgr], planned_start_date=day(p_start), planned_end_date=day(max(p_end, p_start)),
                actual_end_date=day(actual), forecast_end_date=day(ms_forecast), status_code=ms_status,
                progress_pct=ms_progress, is_major=1 if stage.name_en in fx.MAJOR_STAGES else 0, sort_order=i + 1))
            milestone_count += 1
    for code, notes in fx.HEALTH_NOTES.items():
        for dimension, (rag, r_en, r_ar) in notes.items():
            _add(admin, ProjectHealthNote(project_id=projects[code], dimension=dimension, rag=rag, reason_en=r_en,
                                          reason_ar=r_ar))
    for (code, prj, en, ar, category, p, i, owner, m_en, m_ar, due, status) in fx.RISKS:
        _add(admin, Risk(code=code, project_id=projects[prj], title_en=en, title_ar=ar, category=category,
                         probability=p, impact=i, owner_name=fx.PEOPLE[owner], mitigation_en=m_en, mitigation_ar=m_ar,
                         mitigation_due_date=day(due), status_code=status))
    for (code, prj, en, ar, severity, owner, raised, target, escalated, status, r_en, r_ar) in fx.ISSUES:
        _add(admin, Issue(code=code, project_id=projects[prj], title_en=en, title_ar=ar, severity=severity,
                          owner_name=fx.PEOPLE[owner], raised_date=day(raised), target_date=day(target),
                          is_escalated=1 if escalated else 0, status_code=status, resolution_en=r_en,
                          resolution_ar=r_ar))
    _seed_operations(admin, day, models, projects, dept, sites)
    session.commit()
    _seed_documents(admin, models, projects)
    _seed_schedules(admin, day)

    from ..services import snapshot_service
    snapshots = snapshot_service.seed_history(admin, months=13)
    return {"users": len(fx.MOCK_USERS), "models": len(models), "requirements": len(requirements),
            "assets": sum(counters.values()), "projects": len(projects), "milestones": milestone_count,
            "risks": len(fx.RISKS), "issues": len(fx.ISSUES), "snapshots": snapshots}


def is_empty() -> bool:
    return not context.session().scalar(select(func.count()).select_from(AppUser))


def seed_if_empty() -> dict | None:
    """Demo start-up: an empty database gets the roles and, on a local machine, the whole demo world."""
    _guard_profile()
    from ..core.database import write_intent

    with write_intent():
        if not is_empty():
            return None
        settings = context.settings()
        if settings.is_ldap or not settings.local_env:
            seed_roles()
            context.session().commit()
            return {"roles": len(ref.ROLES)}
        return seed_demo()


def _seed_operations(admin, day, models: dict, projects: dict, dept: dict, sites: dict) -> None:
    """AI functions per model, tests, maintenance orders and development opportunities (fixture_operations)."""
    from ..models import AiTechnology, DevelopmentOpportunity, MaintenanceOrder, ModelAiTech, TestEvent
    from . import fixture_operations as ops

    session = context.session()
    techs = {t.code: t.id for t in session.scalars(select(AiTechnology))}
    for model_code, codes in ops.MODEL_AI.items():
        for code in codes:
            session.add(ModelAiTech(model_id=models[model_code], technology_id=techs[code], created_at=context.now()))
    session.flush()
    for (code, en, ar, model, project, d, site, ttype, offset, status, score, r_en, r_ar) in ops.TESTS:
        _add(admin, TestEvent(code=code, title_en=en, title_ar=ar, model_id=models[model], project_id=projects.get(project),
                              department_id=dept[d], site_id=sites.get(site), test_type=ttype, test_date=day(offset),
                              status_code=status, score=score, result_en=r_en, result_ar=r_ar))
    assets = {a.code: a.id for a in session.scalars(select(Asset))}
    for (code, asset, mtype, en, ar, status, start, expected, actual, progress, cost, shortage, parts) in ops.MAINTENANCE:
        if asset not in assets:
            continue
        _add(admin, MaintenanceOrder(code=code, asset_id=assets[asset], maint_type=mtype, title_en=en, title_ar=ar,
                                     status_code=status, start_date=day(start), expected_end_date=day(expected),
                                     actual_end_date=day(actual), progress_pct=progress, cost=cost,
                                     parts_shortage=shortage, parts_text=parts, performed_by=fx.PEOPLE[6]))
    for (code, model, dtype, en, ar, b_en, b_ar, status, complexity, cost, months, priority, project) in ops.DEVELOPMENT:
        _add(admin, DevelopmentOpportunity(code=code, model_id=models[model], dev_type=dtype, title_en=en, title_ar=ar,
                                           benefit_en=b_en, benefit_ar=b_ar, status_code=status, complexity=complexity,
                                           estimated_cost=cost, duration_months=months, priority=priority,
                                           project_id=projects.get(project)))


# code, English, Arabic, type, linked type, linked code, versions (file name, note)
DOCUMENTS = (
    ("DOC-001", "Falcon-X technical datasheet", "نشرة البيانات الفنية لفالكون-إكس", "DATASHEET", "CAPABILITY_MODEL", "M001",
     (("falcon-x-datasheet.pdf", "Initial issue"), ("falcon-x-datasheet-rev2.pdf", "Endurance figures updated"))),
    ("DOC-002", "Falcon-X airframe replacement contract", "عقد استبدال هياكل فالكون-إكس", "CONTRACT", "PROJECT", "PRJ-006",
     (("ct-2025-003.pdf", None),)),
    ("DOC-003", "Factory acceptance test plan", "خطة اختبار القبول في المصنع", "TEST_REPORT", "PROJECT", "PRJ-006",
     (("fat-plan.pdf", None), ("fat-plan-v2.pdf", "Rescheduled"))),
    ("DOC-004", "Wide-area reconnaissance business case", "دراسة الجدوى لأسطول الاستطلاع", "REPORT", "PROJECT", "PRJ-001",
     (("business-case.pdf", None),)),
    ("DOC-005", "Swarm simulation results", "نتائج محاكاة الأسراب", "TEST_REPORT", "PROJECT", "PRJ-011",
     (("swarm-sim-results.csv", "Run 14"),)),
    ("DOC-006", "Ranger-6 operator manual", "دليل مشغل رينجر-6", "MANUAL", "CAPABILITY_MODEL", "M006",
     (("ranger-6-manual.pdf", None),)),
    ("DOC-007", "Wave Runner coastal trial report", "تقرير التجربة الساحلية لويف رانر", "TEST_REPORT", "PROJECT", "PRJ-007",
     (("coastal-trial.pdf", None),)),
    ("DOC-008", "Rimora ROV inspection certificate", "شهادة فحص ريمورا ROV", "CERTIFICATE", "CAPABILITY_MODEL", "M011",
     (("rimora-certificate.pdf", None),)),
)


def _seed_documents(admin, models: dict, projects: dict) -> None:
    from ..models import Document, DocumentVersion
    from ..services import document_service

    session = context.session()
    for code, en, ar, dtype, etype, ecode, versions in DOCUMENTS:
        entity_id = models[ecode] if etype == "CAPABILITY_MODEL" else projects[ecode]
        department_id = session.get(Project, entity_id).department_id if etype == "PROJECT" else None
        doc = _add(admin, Document(code=code, title_en=en, title_ar=ar, doc_type=dtype, entity_type=etype,
                                   entity_id=entity_id, department_id=department_id, current_version=0))
        for number, (file_name, note) in enumerate(versions, start=1):
            if file_name.endswith(".csv"):
                data = f"run,aircraft,conflicts\n14,6,0\n14,8,3\n# {en} (fictional demo data)\n".encode()
                ctype = "text/csv"
            else:
                data = (b"%PDF-1.4\n% Demonstration document (fictional): " + en.encode()
                        + f" v{number}\n".encode() + b"%%EOF\n")
                ctype = "application/pdf"
            digest = document_service._store(data)
            session.add(DocumentVersion(document_id=doc.id, version_no=number, file_name=file_name, content_type=ctype,
                                        size_bytes=len(data), sha256=digest, note=note, uploaded_at=context.now(),
                                        uploaded_by=admin.id))
            doc.current_version = number
        session.flush()
    session.commit()


def _seed_schedules(admin, day) -> None:
    """The three scheduled reports shown in the brochure."""
    from ..models import ReportSchedule

    for name, key, freq, lang, fmt, time, recipients, offset in (
            ("Monthly leadership report", "leadership-monthly", "MONTHLY", "BILINGUAL", "PPTX", "07:00",
             "command.office@example.gov", 26),
            ("Delayed projects report", "projects-delayed", "WEEKLY", "EN", "XLSX", "08:00", "pmo@example.gov", 22),
            ("Maintenance status report", "maintenance-active", "DAILY", "AR", "XLSX", "06:30",
             "maintenance.cell@example.gov", 19)):
        _add(admin, ReportSchedule(name=name, report_key=key, frequency=freq, language=lang, file_format=fmt,
                                   send_time=time, recipients=recipients, next_run_date=day(offset), is_active=1,
                                   owner_id=admin.id))
    context.session().commit()
