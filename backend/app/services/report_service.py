"""Reports: the catalogue (about 130 predefined reports), the executive summary, the monthly leadership report and the
custom report builder, all run by one engine.

A dataset turns records into flat rows through the same services as the pages, so a report only ever contains what
the user may see (permissions and department scope are inherited). A predefined report is a dataset plus an optional
row filter and an optional grouping; a custom report is the same definition chosen by the user.

A run returns {key, title, header, sections}; sections are 'kpis', 'table' and 'bar'. Every run is logged in REPORT_RUN.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import timedelta

from sqlalchemy import select

from ..core.clock import iso_utc
from ..exceptions import Forbidden, NotFound, ValidationFailed
from ..models import Asset, AssetStatusHistory, Contract, Department, Organization, ReportRun, ReportTemplate
from ..schemas.dto import record_meta, sid
from ..security.auth import (PERM_REPORTS_BUILD, PERM_REPORTS_EXEC, PERM_REPORTS_VIEW, department_scope,
                             has_permission, require_permission)
from . import (asset_service, capability_service, context, dashboard_service, document_service, lookup_service as lk,
               metrics_service, operations_service, project_service, settings_service, snapshot_service,
               testing_service)

LANGS = ("EN", "AR", "BILINGUAL")


def _n(ref, lang):
    """A {nameEn, nameAr} reference in the report language."""
    if not ref:
        return ""
    en = ref.get("nameEn") or ref.get("titleEn") or ref.get("code") or ""
    ar = ref.get("nameAr") or ref.get("titleAr") or en
    return ar if lang == "AR" else f"{en} / {ar}" if lang == "BILINGUAL" else en


def _t(en, ar, lang):
    return ar if lang == "AR" else f"{en} / {ar}" if lang == "BILINGUAL" else en


def _status(domain, code, lang):
    s = lk.statuses(domain).get(code)
    return _t(s.name_en, s.name_ar, lang) if s else (code or "")


# Fixed codes shown in reports, in the report language (the twins of the labels in frontend/js/labels*.js).
_LEVELS = {"CRITICAL": ("Critical", "حرجة"), "HIGH": ("High", "عالية"), "MEDIUM": ("Medium", "متوسطة"), "LOW": ("Low", "منخفضة")}
CODE_LABELS = {
    "priority": _LEVELS,
    "level": _LEVELS,
    "severity": _LEVELS,
    "complexity": {"LOW": ("Low", "منخفض"), "MEDIUM": ("Medium", "متوسط"), "HIGH": ("High", "عالٍ")},
    "riskCategory": {"TECHNICAL": ("Technical", "فنية"), "SCHEDULE": ("Schedule", "زمنية"), "FINANCIAL": ("Financial", "مالية"),
                     "SUPPLY_CHAIN": ("Supply chain", "سلسلة الإمداد"), "COMMERCIAL": ("Commercial / contractual", "تجارية / تعاقدية"),
                     "OPERATIONAL": ("Operational", "تشغيلية"), "ENVIRONMENTAL": ("Environmental", "بيئية"),
                     "REGULATORY": ("Regulatory", "تنظيمية")},
    "testType": {"INTERNAL": ("Internal", "داخلية"), "EXTERNAL": ("External", "خارجية")},
    "maintType": {"PREVENTIVE": ("Preventive", "وقائية"), "CORRECTIVE": ("Corrective", "تصحيحية"),
                  "INSPECTION": ("Inspection", "فحص"), "UPGRADE": ("Upgrade", "ترقية")},
    "devType": {"AI": ("AI upgrade", "ترقية الذكاء الاصطناعي"), "SENSORS": ("Sensors", "المستشعرات"),
                "ENDURANCE": ("Endurance", "التحمل"), "COMMUNICATIONS": ("Communications", "الاتصالات"),
                "AUTONOMY": ("Autonomy", "الاستقلالية"), "PAYLOAD": ("Payload", "الحمولة"), "SECURITY": ("Security", "الأمن"),
                "INTEGRATION": ("Integration", "التكامل"), "OTHER": ("Other", "أخرى")},
    "docType": {"REPORT": ("Report", "تقرير"), "SPECIFICATION": ("Specification", "مواصفات"), "CONTRACT": ("Contract", "عقد"),
                "TEST_REPORT": ("Test report", "تقرير اختبار"), "MANUAL": ("Manual", "دليل"), "CERTIFICATE": ("Certificate", "شهادة"),
                "CORRESPONDENCE": ("Correspondence", "مراسلات"), "PRESENTATION": ("Presentation", "عرض تقديمي"),
                "DATASHEET": ("Datasheet", "نشرة بيانات"), "OTHER": ("Other", "أخرى")},
    "entity": {"CAPABILITY_MODEL": ("Capability model", "نموذج قدرة"), "ASSET": ("Asset", "أصل"), "PROJECT": ("Project", "مشروع"),
               "TEST_EVENT": ("Test", "اختبار"), "MAINTENANCE_ORDER": ("Maintenance", "صيانة"),
               "ORGANIZATION": ("Supplier / manufacturer", "مورد / شركة مصنعة"), "CONTRACT": ("Contract", "عقد"),
               "CAPABILITY_REQUIREMENT": ("Requirement", "متطلب")},
}


def _code(kind, code, lang):
    label = CODE_LABELS[kind].get(code)
    return _t(*label, lang) if label else (code or "")


# ---------------------------------------------------------------- datasets -----------------------------------------
# field: (key, English label, Arabic label, kind, groupable). kind: text | number | percent | date | money

def _assets(actor, lang):
    rows = []
    for a in asset_service.list_assets(actor, {"all": True}, 0, 5000)["items"]:
        rows.append({"code": a["code"], "serial": a["serialNumber"] or "", "model": _n(a["model"], lang),
                     "category": (a["category"] or {}).get("code", ""), "department": _n(a["department"], lang),
                     "site": _n(a["site"], lang), "status": _status("ASSET", a["status"], lang), "_status": a["status"],
                     "manufacturer": _n(a["manufacturer"], lang), "operational": a["readiness"]["operational"],
                     "overall": a["readiness"]["overall"], "acquired": a["acquisitionDate"],
                     "year": a["acquisitionDate"][:4] if a["acquisitionDate"] else "", "delivery": a["expectedDeliveryDate"],
                     "warranty": a["warrantyEndDate"], "age": a["ageYears"]})
    return rows


def _models(actor, lang):
    rows = []
    for m in capability_service.list_models(actor):
        counts = m["assetCounts"]["byStatus"]
        rows.append({"code": m["code"], "model": _n(m, lang), "category": (m["category"] or {}).get("code", ""),
                     "manufacturer": _n(m["manufacturer"], lang), "role": _t(m["roleEn"] or "", m["roleAr"] or "", lang),
                     "assets": m["assetCounts"]["total"], "ready": counts.get("READY", 0) + counts.get("READY_LIMITED", 0),
                     "unitCost": m["unitCost"]})
    return rows


def _requirements(actor, lang):
    return [{"code": r["code"], "requirement": _n(r, lang), "department": _n(r["department"], lang),
             "category": r["category"]["code"], "priority": _code("priority", r["priority"], lang), "required": r["required"],
             "available": r["available"], "operational": r["operational"], "pipeline": r["pipelineTotal"],
             "gap": r["gap"], "forecastGap": r["forecastGap"], "current": r["currentPct"], "forecast": r["forecastPct"],
             "critical": _t("Yes", "نعم", lang) if r["critical"] else _t("No", "لا", lang), "_critical": r["critical"]}
            for r in metrics_service.requirement_metrics(actor)]


def _projects(actor, lang):
    rows = []
    for p in project_service.portfolio(actor, {})["items"]:
        rows.append({"code": p["code"], "project": _n(p, lang), "type": _n(p["type"], lang),
                     "department": _n(p["department"], lang), "category": (p["category"] or {}).get("code", ""),
                     "status": _status("PROJECT", p["status"], lang), "_status": p["status"], "stage": _n(p["stage"], lang),
                     "manager": p["managerName"] or "", "progress": p["progressPct"], "budget": p["budget"],
                     "spend": p["actualSpend"], "target": p["targetEndDate"], "forecast": p["forecastEndDate"],
                     "delay": p["delayDays"], "health": {"GREEN": _t("Green", "أخضر", lang), "AMBER": _t("Amber", "كهرماني", lang),
                                                         "RED": _t("Red", "أحمر", lang)}[p["health"]], "_health": p["health"]})
    return rows


def _milestones(actor, lang):
    return [{"project": m["project"]["code"], "milestone": _n(m, lang), "department": _n(m["project"]["department"], lang),
             "owner": m["ownerName"] or "", "plannedEnd": m["plannedEndDate"], "forecast": m["forecastEndDate"],
             "actual": m["actualEndDate"], "status": _status("MILESTONE", m["status"], lang), "_status": m["status"],
             "slip": m["slipDays"], "progress": m["progressPct"], "_overdue": m["overdue"], "_major": m["major"]}
            for m in project_service.list_milestones(actor, {})["items"]]


def _risks(actor, lang):
    return [{"code": r["code"], "project": r["project"]["code"], "department": _n(r["project"]["department"], lang),
             "risk": _t(r["titleEn"], r["titleAr"], lang), "category": _code("riskCategory", r["category"], lang), "probability": r["probability"],
             "impact": r["impact"], "score": r["score"], "level": _code("level", r["level"], lang), "_level": r["level"], "owner": r["ownerName"] or "",
             "due": r["mitigationDueDate"], "status": _status("RISK", r["status"], lang), "_status": r["status"],
             "_overdue": r["mitigationOverdue"]}
            for r in project_service.list_risks(actor, {})["items"]]


def _issues(actor, lang):
    return [{"code": i["code"], "project": i["project"]["code"], "department": _n(i["project"]["department"], lang),
             "issue": _t(i["titleEn"], i["titleAr"], lang), "severity": _code("severity", i["severity"], lang), "owner": i["ownerName"] or "",
             "raised": i["raisedDate"], "target": i["targetDate"], "status": _status("ISSUE", i["status"], lang),
             "_status": i["status"], "escalated": _t("Yes", "نعم", lang) if i["escalated"] else _t("No", "لا", lang),
             "_escalated": i["escalated"], "_overdue": i["overdue"]}
            for i in project_service.list_issues(actor, {})["items"]]


def _tests(actor, lang):
    return [{"code": e["code"], "test": _t(e["titleEn"], e["titleAr"], lang), "model": _n(e["model"], lang),
             "department": _n(e["department"], lang), "type": _code("testType", e["testType"], lang), "date": e["testDate"],
             "status": _status("TEST", e["status"], lang), "_status": e["status"], "score": e["score"],
             "project": (e["project"] or {}).get("code", "")}
            for e in testing_service.list_tests(actor, {})["items"]]


def _maintenance(actor, lang):
    return [{"code": m["code"], "asset": m["asset"]["code"], "model": _n(m["model"], lang), "department": _n(m["department"], lang),
             "type": _code("maintType", m["type"], lang), "work": _t(m["titleEn"], m["titleAr"], lang), "status": _status("MAINTENANCE", m["status"], lang),
             "_status": m["status"], "start": m["startDate"], "expected": m["expectedEndDate"], "progress": m["progressPct"],
             "cost": m["cost"], "downtime": m["downtimeDays"], "_overdue": m["overdue"], "_parts": m["partsShortage"]}
            for m in operations_service.maintenance(actor, {})["items"]]


def _development(actor, lang):
    return [{"code": o["code"], "model": _n(o["model"], lang), "type": _code("devType", o["type"], lang), "opportunity": _t(o["titleEn"], o["titleAr"], lang),
             "status": _status("DEVELOPMENT", o["status"], lang), "_status": o["status"], "complexity": _code("complexity", o["complexity"], lang),
             "cost": o["estimatedCost"], "months": o["durationMonths"], "priority": _code("priority", o["priority"], lang),
             "project": (o["project"] or {}).get("code", "")}
            for o in operations_service.development(actor, {})["items"]]


def _documents(actor, lang):
    return [{"code": d["code"], "document": _t(d["titleEn"], d["titleAr"], lang), "type": _code("docType", d["docType"], lang),
             "linkedType": _code("entity", d["linked"]["type"], lang), "linked": d["linked"]["code"], "version": d["currentVersion"],
             "date": d["latest"]["uploadedAt"][:10] if d["latest"] else None}
            for d in document_service.list_documents(actor, {})["items"]]


def _suppliers(actor, lang):
    session = context.session()
    contracts = Counter(c.supplier_id for c in session.scalars(select(Contract).where(Contract.archived_at.is_(None))))
    return [{"code": o.code, "organization": _t(o.name_en, o.name_ar, lang), "kind": o.kind,
             "country": _t(o.country_en or "", o.country_ar or "", lang), "contracts": contracts.get(o.id, 0)}
            for o in session.scalars(select(Organization).where(Organization.archived_at.is_(None)).order_by(Organization.code))]


def _contracts(actor, lang):
    return [{"code": c.code, "contract": _t(c.title_en, c.title_ar, lang),
             "supplier": _n(lk.ref_id(Organization, c.supplier_id), lang), "value": c.contract_value,
             "start": c.start_date.isoformat() if c.start_date else None, "end": c.end_date.isoformat() if c.end_date else None}
            for c in context.session().scalars(select(Contract).where(Contract.archived_at.is_(None)).order_by(Contract.code))]


def _ai_models(actor, lang):
    data = operations_service.ai_overview(actor)
    return [{"model": _n(m["model"], lang), "category": (m["category"] or {}).get("code", ""), "level": m["level"],
             "functions": len(m["supported"])} for m in data["models"]]


def F(key, en, ar, kind="text", group=False):
    return (key, en, ar, kind, group)


DATASETS = {
    "assets": (_assets, _t, [F("code", "Asset ID", "رقم الأصل"), F("serial", "Serial number", "الرقم التسلسلي"),
               F("model", "Model", "النموذج", group=True), F("category", "Category", "الفئة", group=True),
               F("department", "Department", "الإدارة", group=True), F("site", "Location", "الموقع", group=True),
               F("status", "Status", "الحالة", group=True), F("manufacturer", "Manufacturer", "الشركة المصنعة", group=True),
               F("operational", "Operational readiness", "الجاهزية العملياتية", "percent"),
               F("overall", "Overall readiness", "الجاهزية الإجمالية", "percent"),
               F("acquired", "Acquisition date", "تاريخ الاقتناء", "date"), F("year", "Acquisition year", "سنة الاقتناء", group=True),
               F("delivery", "Expected delivery", "موعد التسليم", "date"), F("warranty", "Warranty end", "انتهاء الضمان", "date"),
               F("age", "Age (years)", "العمر (سنوات)", "number")]),
    "models": (_models, _t, [F("code", "ID", "المعرّف"), F("model", "Model", "النموذج"), F("category", "Category", "الفئة", group=True),
               F("manufacturer", "Manufacturer", "الشركة المصنعة", group=True), F("role", "Role", "الدور"),
               F("assets", "Assets", "الأصول", "number"), F("ready", "Ready", "الجاهزة", "number"),
               F("unitCost", "Unit cost", "تكلفة الوحدة", "money")]),
    "requirements": (_requirements, _t, [F("code", "ID", "المعرّف"), F("requirement", "Requirement", "المتطلب"),
               F("department", "Department", "الإدارة", group=True), F("category", "Category", "الفئة", group=True),
               F("priority", "Priority", "الأولوية", group=True), F("required", "Required", "المطلوب", "number"),
               F("available", "Available", "المتوفر", "number"), F("operational", "Operational", "الجاهز", "number"),
               F("pipeline", "In preparation", "قيد الإعداد", "number"), F("gap", "Current gap", "الفجوة الحالية", "number"),
               F("forecastGap", "Forecast gap", "الفجوة المتوقعة", "number"), F("current", "Current completion", "الاستكمال الحالي", "percent"),
               F("forecast", "Forecast completion", "الاستكمال المتوقع", "percent"), F("critical", "Critical gap", "فجوة حرجة", group=True)]),
    "projects": (_projects, _t, [F("code", "Project ID", "رقم المشروع"), F("project", "Project", "المشروع"),
               F("type", "Type", "النوع", group=True), F("department", "Department", "الإدارة", group=True),
               F("category", "Category", "الفئة", group=True), F("status", "Status", "الحالة", group=True),
               F("stage", "Stage", "المرحلة", group=True), F("manager", "Manager", "مدير المشروع", group=True),
               F("progress", "Progress", "الإنجاز", "percent"), F("budget", "Budget", "الميزانية", "money"),
               F("spend", "Spend", "الصرف", "money"), F("target", "Target date", "الموعد المستهدف", "date"),
               F("forecast", "Forecast date", "الموعد المتوقع", "date"), F("delay", "Days late", "أيام التأخير", "number"),
               F("health", "Health", "السلامة", group=True)]),
    "milestones": (_milestones, _t, [F("project", "Project", "المشروع", group=True), F("milestone", "Milestone", "المرحلة"),
               F("department", "Department", "الإدارة", group=True), F("owner", "Owner", "المسؤول", group=True),
               F("plannedEnd", "Planned end", "الانتهاء المخطط", "date"), F("forecast", "Forecast", "المتوقع", "date"),
               F("actual", "Actual", "الفعلي", "date"), F("status", "Status", "الحالة", group=True),
               F("slip", "Slip (days)", "التأخير (أيام)", "number"), F("progress", "Progress", "الإنجاز", "percent")]),
    "risks": (_risks, _t, [F("code", "Risk ID", "رقم الخطر"), F("project", "Project", "المشروع", group=True),
               F("department", "Department", "الإدارة", group=True), F("risk", "Risk", "الخطر"),
               F("category", "Category", "الفئة", group=True), F("probability", "Probability", "الاحتمالية", "number"),
               F("impact", "Impact", "الأثر", "number"), F("score", "Score", "الدرجة", "number"), F("level", "Level", "المستوى", group=True),
               F("owner", "Owner", "المسؤول", group=True), F("due", "Mitigation due", "موعد المعالجة", "date"),
               F("status", "Status", "الحالة", group=True)]),
    "issues": (_issues, _t, [F("code", "Issue ID", "رقم المشكلة"), F("project", "Project", "المشروع", group=True),
               F("department", "Department", "الإدارة", group=True), F("issue", "Issue", "المشكلة"),
               F("severity", "Severity", "الخطورة", group=True), F("owner", "Owner", "المسؤول", group=True),
               F("raised", "Raised", "تاريخ الرصد", "date"), F("target", "Target", "الموعد المستهدف", "date"),
               F("status", "Status", "الحالة", group=True), F("escalated", "Escalated", "مصعّدة", group=True)]),
    "tests": (_tests, _t, [F("code", "Test ID", "رقم الاختبار"), F("test", "Test", "الاختبار"), F("model", "Model", "النموذج", group=True),
               F("department", "Department", "الإدارة", group=True), F("type", "Type", "النوع", group=True),
               F("date", "Date", "التاريخ", "date"), F("status", "Result", "النتيجة", group=True), F("score", "Score", "الدرجة", "number"),
               F("project", "Project", "المشروع", group=True)]),
    "maintenance": (_maintenance, _t, [F("code", "Order", "الأمر"), F("asset", "Asset", "الأصل"), F("model", "Model", "النموذج", group=True),
               F("department", "Department", "الإدارة", group=True), F("type", "Type", "النوع", group=True), F("work", "Work", "العمل"),
               F("status", "Status", "الحالة", group=True), F("start", "Start", "البدء", "date"), F("expected", "Expected end", "الإنجاز المتوقع", "date"),
               F("progress", "Progress", "الإنجاز", "percent"), F("cost", "Cost", "التكلفة", "money"), F("downtime", "Downtime (days)", "التوقف (أيام)", "number")]),
    "development": (_development, _t, [F("code", "ID", "المعرّف"), F("model", "Model", "النموذج", group=True), F("type", "Type", "النوع", group=True),
               F("opportunity", "Opportunity", "الفرصة"), F("status", "Status", "الحالة", group=True), F("complexity", "Complexity", "التعقيد", group=True),
               F("cost", "Estimated cost", "التكلفة التقديرية", "money"), F("months", "Months", "الأشهر", "number"),
               F("priority", "Priority", "الأولوية", group=True), F("project", "Project", "المشروع", group=True)]),
    "documents": (_documents, _t, [F("code", "Document ID", "معرّف المستند"), F("document", "Document", "المستند"),
               F("type", "Type", "النوع", group=True), F("linkedType", "Linked to", "مرتبط بـ", group=True),
               F("linked", "Record", "السجل"), F("version", "Version", "الإصدار", "number"), F("date", "Last upload", "آخر رفع", "date")]),
    "suppliers": (_suppliers, _t, [F("code", "ID", "المعرّف"), F("organization", "Organisation", "الجهة"), F("kind", "Kind", "النوع", group=True),
               F("country", "Country", "الدولة", group=True), F("contracts", "Contracts", "العقود", "number")]),
    "contracts": (_contracts, _t, [F("code", "Contract", "العقد"), F("contract", "Title", "العنوان"), F("supplier", "Supplier", "المورد", group=True),
               F("value", "Value", "القيمة", "money"), F("start", "Start", "البداية", "date"), F("end", "End", "النهاية", "date")]),
    "aiModels": (_ai_models, _t, [F("model", "Model", "النموذج"), F("category", "Category", "الفئة", group=True),
               F("level", "AI level", "مستوى الذكاء الاصطناعي", "number", group=True), F("functions", "AI functions", "وظائف الذكاء الاصطناعي", "number")]),
}

# ---------------------------------------------------------------- the catalogue ------------------------------------
# report: key -> {category, titleEn, titleAr, dataset, group, where (row predicate), columns, perm}

CATEGORIES = {
    "executive": ("Executive reports", "التقارير التنفيذية"), "capabilities": ("Capability reports", "تقارير القدرات"),
    "assets": ("Asset reports", "تقارير الأصول"), "projects": ("Project reports", "تقارير المشاريع"),
    "risks": ("Risk and issue reports", "تقارير المخاطر والمشكلات"), "testing": ("Testing reports", "تقارير التجارب"),
    "maintenance": ("Maintenance reports", "تقارير الصيانة"), "ai": ("AI and development reports", "تقارير الذكاء الاصطناعي والتطوير"),
    "suppliers": ("Supplier and contract reports", "تقارير الموردين والعقود"), "documents": ("Document reports", "تقارير المستندات"),
    "trends": ("Trend analysis", "تحليلات الاتجاهات"),
}
_DATASET_CATEGORY = {"assets": "assets", "models": "capabilities", "requirements": "capabilities", "projects": "projects",
                     "milestones": "projects", "risks": "risks", "issues": "risks", "tests": "testing",
                     "maintenance": "maintenance", "development": "ai", "aiModels": "ai", "documents": "documents",
                     "suppliers": "suppliers", "contracts": "suppliers"}
_DATASET_NAMES = {"assets": ("Assets", "الأصول"), "models": ("Capability models", "نماذج القدرات"),
                  "requirements": ("Capability requirements", "متطلبات القدرات"), "projects": ("Projects", "المشاريع"),
                  "milestones": ("Milestones", "المراحل الرئيسية"), "risks": ("Risks", "المخاطر"), "issues": ("Issues", "المشكلات"),
                  "tests": ("Tests", "التجارب"), "maintenance": ("Maintenance", "الصيانة"),
                  "development": ("Development opportunities", "فرص التطوير"), "documents": ("Documents", "المستندات"),
                  "suppliers": ("Suppliers and manufacturers", "الموردون والشركات المصنعة"), "contracts": ("Contracts", "العقود"),
                  "aiModels": ("AI capability by model", "قدرات الذكاء الاصطناعي حسب النموذج")}

DECISION_PANELS = {
    "criticalGaps": ("Critical capability gaps", "فجوات القدرات الحرجة"),
    "projectsAtRisk": ("Projects at risk", "المشاريع المعرضة للخطر"),
    "replacement": ("Capabilities requiring replacement", "قدرات تتطلب الاستبدال"),
    "maintenance": ("Maintenance bottlenecks", "اختناقات الصيانة"),
    "deliveries": ("Upcoming deliveries", "التسليمات القادمة"),
    "tests": ("Upcoming tests", "الاختبارات القادمة"),
    "lowReadiness": ("Readiness by department", "الجاهزية حسب الإدارة"),
    "budget": ("Budget overruns", "تجاوزات الميزانية"),
    "warranty": ("Warranties ending", "ضمانات تنتهي قريباً"),
    "opportunities": ("Unfunded high-priority opportunities", "فرص عالية الأولوية دون تمويل"),
    "overdueMitigations": ("Overdue risk mitigations", "إجراءات معالجة مخاطر متأخرة"),
}

TREND_METRICS = (("assets_total", "Total assets", "إجمالي الأصول"), ("assets_operational", "Ready assets", "الأصول الجاهزة"),
                 ("assets_maintenance", "Assets under maintenance", "الأصول قيد الصيانة"),
                 ("assets_not_ready", "Assets not ready", "الأصول غير الجاهزة"),
                 ("completion_current", "Current completion %", "الاستكمال الحالي %"),
                 ("completion_forecast", "Forecast completion %", "الاستكمال المتوقع %"),
                 ("critical_gaps", "Critical gaps", "الفجوات الحرجة"), ("projects_delayed", "Delayed projects", "المشاريع المتأخرة"),
                 ("readiness_avg", "Average readiness %", "متوسط الجاهزية %"))


def _named_filters():
    today = lambda: context.today().isoformat()  # noqa: E731
    in_days = lambda n: (context.today() + timedelta(days=n)).isoformat()  # noqa: E731
    available = lambda: set(settings_service.get("assets.available_statuses"))  # noqa: E731
    pipeline = lambda: set(settings_service.get("assets.pipeline_statuses"))  # noqa: E731
    return [
        ("assets", "ready", "Ready capabilities", "القدرات الجاهزة", lambda r: r["_status"] in ("READY", "READY_LIMITED")),
        ("assets", "not-ready", "Capabilities not ready", "القدرات غير الجاهزة", lambda r: r["_status"] in ("NOT_READY", "TEMP_NOT_READY")),
        ("assets", "maintenance", "Assets under maintenance", "الأصول قيد الصيانة", lambda r: r["_status"] == "UNDER_MAINTENANCE"),
        ("assets", "pipeline", "Assets in preparation", "الأصول قيد الإعداد", lambda r: r["_status"] in pipeline()),
        ("assets", "available", "Available assets", "الأصول المتوفرة", lambda r: r["_status"] in available()),
        ("assets", "replacement", "Assets awaiting replacement", "الأصول بانتظار الاستبدال", lambda r: r["_status"] == "AWAITING_REPLACEMENT"),
        ("assets", "written-off", "Written-off assets", "الأصول المشطوبة", lambda r: r["_status"] == "WRITTEN_OFF"),
        ("assets", "warranty-90", "Warranties ending within 90 days", "ضمانات تنتهي خلال 90 يوماً",
         lambda r: r["warranty"] and today() <= r["warranty"] <= in_days(90)),
        ("assets", "old", "Assets older than the replacement age", "أصول تجاوزت عمر الاستبدال",
         lambda r: (r["age"] or 0) > settings_service.get("assets.replacement_age_years")),
        ("requirements", "critical-gaps", "Critical capability gaps", "فجوات القدرات الحرجة", lambda r: r["_critical"]),
        ("requirements", "gaps", "Capability gaps register", "سجل فجوات القدرات", lambda r: r["gap"] > 0),
        ("requirements", "closed", "Requirements fully met", "متطلبات مستوفاة بالكامل", lambda r: r["gap"] == 0),
        ("projects", "active", "Active projects", "المشاريع النشطة", lambda r: r["_status"] not in ("COMPLETED", "CANCELLED")),
        ("projects", "delayed", "Delayed projects", "المشاريع المتأخرة", lambda r: (r["delay"] or 0) > 0),
        ("projects", "red", "Projects with red health", "مشاريع سلامتها حمراء", lambda r: r["_health"] == "RED"),
        ("projects", "completed", "Completed projects", "المشاريع المكتملة", lambda r: r["_status"] == "COMPLETED"),
        ("projects", "due-90", "Projects completing within 90 days", "مشاريع تكتمل خلال 90 يوماً",
         lambda r: r["forecast"] and today() <= r["forecast"] <= in_days(90)),
        ("milestones", "overdue", "Overdue milestones", "المراحل المتأخرة", lambda r: r["_overdue"]),
        ("milestones", "next-90", "Milestones due within 90 days", "مراحل تستحق خلال 90 يوماً",
         lambda r: r["_status"] != "COMPLETED" and r["plannedEnd"] and today() <= r["plannedEnd"] <= in_days(90)),
        ("milestones", "major", "Major milestones", "المراحل الرئيسية", lambda r: r["_major"]),
        ("risks", "critical", "Critical risks", "المخاطر الحرجة", lambda r: r["_level"] == "CRITICAL" and r["_status"] != "CLOSED"),
        ("risks", "overdue", "Overdue mitigations", "إجراءات المعالجة المتأخرة", lambda r: r["_overdue"]),
        ("risks", "open", "Open risks", "المخاطر المفتوحة", lambda r: r["_status"] != "CLOSED"),
        ("issues", "escalated", "Issues requiring escalation", "مشكلات تتطلب التصعيد", lambda r: r["_escalated"]),
        ("issues", "overdue", "Issues past their target date", "مشكلات تجاوزت موعدها", lambda r: r["_overdue"]),
        ("tests", "failed", "Failed and conditional tests", "الاختبارات الراسبة والمشروطة", lambda r: r["_status"] in ("FAILED", "CONDITIONAL")),
        ("tests", "upcoming", "Upcoming tests", "الاختبارات القادمة", lambda r: r["_status"] == "PLANNED"),
        ("maintenance", "overdue", "Overdue maintenance", "الصيانة المتأخرة", lambda r: r["_overdue"]),
        ("maintenance", "parts", "Spare-part shortages", "نقص قطع الغيار", lambda r: r["_parts"]),
        ("maintenance", "active", "Active maintenance", "الصيانة الجارية", lambda r: r["_status"] not in ("COMPLETED", "CANCELLED")),
        ("development", "unfunded", "Opportunities without a project", "فرص دون مشروع", lambda r: not r["project"]),
        ("contracts", "ending", "Contracts ending within 180 days", "عقود تنتهي خلال 180 يوماً",
         lambda r: r["end"] and today() <= r["end"] <= in_days(180)),
    ]


def catalogue() -> dict[str, dict]:
    reports: dict[str, dict] = {}

    def add(key, category, en, ar, perm=PERM_REPORTS_VIEW, **spec):
        reports[key] = {"key": key, "category": category, "titleEn": en, "titleAr": ar, "perm": perm, **spec}

    add("executive-summary", "executive", "Executive capability summary", "ملخص القدرات التنفيذي", PERM_REPORTS_EXEC, special="executive")
    add("leadership-monthly", "executive", "Monthly leadership report", "التقرير الشهري للقيادة", PERM_REPORTS_EXEC, special="monthly")
    add("readiness-current", "executive", "Current operational readiness", "الجاهزية العملياتية الحالية", PERM_REPORTS_EXEC, special="readiness")
    add("decision-support", "executive", "Decision support summary", "ملخص دعم القرار", PERM_REPORTS_EXEC, special="decision")
    for name, (_, _, fields) in DATASETS.items():
        en, ar = _DATASET_NAMES[name]
        cat = _DATASET_CATEGORY[name]
        add(f"{name}-register", cat, f"{en} register", f"سجل {ar}", dataset=name)
        for key, f_en, f_ar, _kind, group in fields:
            if group:
                add(f"{name}-by-{key}", cat, f"{en} by {f_en.lower()}", f"{ar} حسب {f_ar}", dataset=name, group=key)
    for name, key, en, ar, where in _named_filters():
        add(f"{name}-{key}", _DATASET_CATEGORY[name], en, ar, dataset=name, where=where)
    for metric, en, ar in TREND_METRICS:
        add(f"trend-{metric}", "trends", f"Trend: {en}", f"الاتجاه: {ar}", special="trend", metric=metric)
    return reports


_CATALOGUE: dict | None = None


def _cat() -> dict:
    global _CATALOGUE
    if _CATALOGUE is None:
        _CATALOGUE = catalogue()
    return _CATALOGUE


def list_reports(actor) -> dict:
    require_permission(actor, PERM_REPORTS_VIEW)
    items = [{"key": r["key"], "category": r["category"], "titleEn": r["titleEn"], "titleAr": r["titleAr"]}
             for r in _cat().values() if has_permission(actor, r["perm"])]
    return {"items": items, "categories": [{"key": k, "titleEn": en, "titleAr": ar} for k, (en, ar) in CATEGORIES.items()],
            "total": len(items)}


def dataset_fields() -> dict:
    return {name: {"titleEn": _DATASET_NAMES[name][0], "titleAr": _DATASET_NAMES[name][1],
                   "fields": [{"key": k, "labelEn": en, "labelAr": ar, "kind": kind, "group": group}
                              for k, en, ar, kind, group in fields]}
            for name, (_, _, fields) in DATASETS.items()}


# ---------------------------------------------------------------- the engine ---------------------------------------


def _columns(dataset: str, keys: list[str] | None, lang: str) -> list[dict]:
    fields = DATASETS[dataset][2]
    chosen = [f for f in fields if keys is None or f[0] in keys]
    if keys:
        chosen.sort(key=lambda f: keys.index(f[0]))
    return [{"key": k, "label": _t(en, ar, lang), "kind": kind} for k, en, ar, kind, _ in chosen]


def _clean(rows: list[dict]) -> list[dict]:
    return [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows]


def _grouped(dataset: str, rows: list[dict], group: str, lang: str) -> list[dict]:
    fields = DATASETS[dataset][2]
    numeric = [(k, en, ar, kind) for k, en, ar, kind, _ in fields if kind in ("number", "money", "percent") and k != group]
    label = next(_t(en, ar, lang) for k, en, ar, _, _ in fields if k == group)
    buckets: dict = defaultdict(list)
    for r in rows:
        buckets[str(r.get(group) if r.get(group) not in (None, "") else "—")].append(r)
    columns = [{"key": "group", "label": label, "kind": "text"}, {"key": "count", "label": _t("Records", "السجلات", lang), "kind": "number"}]
    out_rows = []
    for g, items in sorted(buckets.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        row = {"group": g, "count": len(items)}
        for k, en, ar, kind in numeric:
            values = [i[k] for i in items if isinstance(i.get(k), (int, float))]
            row[k] = (round(sum(values) / len(values), 1) if kind == "percent" else round(sum(values), 2)) if values else None
        out_rows.append(row)
    for k, en, ar, kind in numeric:
        prefix = _t("Average", "متوسط", lang) if kind == "percent" else _t("Total", "إجمالي", lang)
        columns.append({"key": k, "label": f"{prefix} {_t(en, ar, lang)}", "kind": kind})
    return [{"kind": "bar", "title": label, "items": [{"label": r["group"], "value": r["count"]} for r in out_rows]},
            {"kind": "table", "title": label, "columns": columns, "rows": out_rows}]


def _header(actor, title_en, title_ar, lang, filters: dict) -> dict:
    classification = settings_service.get("reports.classification")
    scope = department_scope(actor)
    return {"titleEn": title_en, "titleAr": title_ar, "generatedAt": iso_utc(context.now()), "generatedBy": actor.display_name,
            "role": _t(actor.role.name_en, actor.role.name_ar, lang) if actor.role else actor.role_code,
            "asOf": context.today().isoformat(), "language": lang,
            "classification": _t(classification["en"], classification["ar"], lang),
            "filters": filters, "scope": "ALL" if scope is None else "DEPARTMENT"}


def run_definition(actor, definition: dict, lang: str, title_en: str, title_ar: str, key: str) -> dict:
    """definition: {dataset, columns?, group?, filters? {field: value}, sort?, where? (python predicate, catalogue only)}"""
    dataset = definition.get("dataset")
    if dataset not in DATASETS:
        raise ValidationFailed.field("dataset", "Unknown dataset.")
    rows = DATASETS[dataset][0](actor, lang)
    if definition.get("where"):
        rows = [r for r in rows if definition["where"](r)]
    filters = definition.get("filters") or {}
    field_keys = {f[0] for f in DATASETS[dataset][2]}
    for k, v in filters.items():
        if k not in field_keys:
            raise ValidationFailed.field("filters", f"Unknown field {k}.")
        if v not in (None, ""):
            rows = [r for r in rows if str(r.get(k) or "") == str(v)]
    sort = definition.get("sort")
    if sort and sort in field_keys:
        rows.sort(key=lambda r: (r.get(sort) is None, r.get(sort) if r.get(sort) is not None else 0), reverse=bool(definition.get("desc")))
    header = _header(actor, title_en, title_ar, lang, filters)
    sections = [{"kind": "kpis", "items": [{"label": _t("Records", "السجلات", lang), "value": len(rows)}]}]
    if definition.get("group"):
        if definition["group"] not in field_keys:
            raise ValidationFailed.field("group", "Unknown field.")
        sections += _grouped(dataset, rows, definition["group"], lang)
    else:
        columns = _columns(dataset, definition.get("columns"), lang)
        sections.append({"kind": "table", "title": _t(*_DATASET_NAMES[dataset], lang), "columns": columns,
                         "rows": _clean(rows)})
    return {"key": key, "titleEn": title_en, "titleAr": title_ar, "header": header, "sections": sections,
            "rowCount": len(rows)}


def _special(actor, report: dict, lang: str) -> dict:
    kind = report["special"]
    header = _header(actor, report["titleEn"], report["titleAr"], lang, {})
    sections = []
    if kind in ("executive", "readiness"):
        d = dashboard_service.dashboard(actor)
        labels = {"capabilities": ("Total capabilities", "إجمالي القدرات"), "assets": ("Total assets", "إجمالي الأصول"),
                  "ready": ("Ready assets", "الأصول الجاهزة"), "maintenance": ("Under maintenance", "قيد الصيانة"),
                  "notReady": ("Not ready", "غير جاهزة"), "awaiting": ("Awaiting replacement", "بانتظار الاستبدال"),
                  "writtenOff": ("Written off", "مشطوبة"), "acquisition": ("Under acquisition", "قيد الاقتناء"),
                  "development": ("Under development", "قيد التطوير"), "test": ("Under test", "قيد الاختبار"),
                  "criticalGaps": ("Critical gaps", "الفجوات الحرجة"), "activeProjects": ("Current projects", "المشاريع الحالية"),
                  "devProjects": ("Projects in development", "مشاريع قيد التطوير"), "testProjects": ("Projects in testing", "مشاريع قيد الاختبار"),
                  "delayedProjects": ("Delayed projects", "المشاريع المتأخرة"), "due30": ("Completing within 30 days", "تكتمل خلال 30 يوماً"),
                  "due90": ("Completing within 90 days", "تكتمل خلال 90 يوماً")}
        for block, (en, ar) in (("inventory", ("Inventory", "المخزون")), ("pipeline", ("In preparation", "قيد الإعداد")),
                                ("portfolio", ("Portfolio", "المحفظة"))):
            if kind == "readiness" and block == "portfolio":
                continue
            sections.append({"kind": "kpis", "title": _t(en, ar, lang), "items": [
                {"label": _t(*labels[k], lang), "value": v["value"], "trend": v.get("trend")} for k, v in d[block].items()]})
        sections.append({"kind": "table", "title": _t("Completion by department", "الاستكمال حسب الإدارة", lang),
                         "columns": [{"key": "department", "label": _t("Department", "الإدارة", lang), "kind": "text"},
                                     {"key": "required", "label": _t("Required", "المطلوب", lang), "kind": "number"},
                                     {"key": "available", "label": _t("Available", "المتوفر", lang), "kind": "number"},
                                     {"key": "gap", "label": _t("Current gap", "الفجوة الحالية", lang), "kind": "number"},
                                     {"key": "current", "label": _t("Current completion", "الاستكمال الحالي", lang), "kind": "percent"},
                                     {"key": "forecast", "label": _t("Forecast completion", "الاستكمال المتوقع", lang), "kind": "percent"}],
                         "rows": [{"department": _n(g["department"], lang), "required": g["required"], "available": g["available"],
                                   "gap": g["gap"], "current": g["currentPct"], "forecast": g["forecastPct"]}
                                  for g in d["completion"]["groups"]]})
        if kind == "executive":
            sections.append({"kind": "list", "title": _t("Items requiring leadership attention", "بنود تتطلب اهتمام القيادة", lang),
                             "items": [_t(a["textEn"], a["textAr"], lang) for a in d["attention"]]})
        else:
            m = operations_service.maintenance(actor, {})
            sections.append({"kind": "table", "title": _t("Readiness by department", "الجاهزية حسب الإدارة", lang),
                             "columns": [{"key": "department", "label": _t("Department", "الإدارة", lang), "kind": "text"},
                                         {"key": "operational", "label": _t("Operational", "العملياتية", lang), "kind": "percent"},
                                         {"key": "technical", "label": _t("Technical", "الفنية", lang), "kind": "percent"},
                                         {"key": "mission", "label": _t("Mission", "المهمة", lang), "kind": "percent"},
                                         {"key": "maintenance", "label": _t("Maintenance", "الصيانة", lang), "kind": "percent"}],
                             "rows": [{"department": _n(r["department"], lang), **{k: r[k] for k in ("operational", "technical", "mission", "maintenance")}}
                                      for r in m["readinessByDepartment"]]})
    elif kind == "monthly":
        current = snapshot_service.current_values(actor)
        month_ago = context.today() - timedelta(days=30)
        rows = []
        for metric, en, ar in TREND_METRICS:
            prev = snapshot_service.value_on_or_before(metric, None, month_ago)
            cur = current.get(metric)
            rows.append({"metric": _t(en, ar, lang), "previous": prev, "current": cur,
                         "change": None if prev is None or cur is None else round(cur - prev, 1)})
        sections.append({"kind": "table", "title": _t("Main changes since last month", "أبرز التغيرات منذ الشهر السابق", lang),
                         "columns": [{"key": "metric", "label": _t("Measure", "المقياس", lang), "kind": "text"},
                                     {"key": "previous", "label": _t("Last month", "الشهر السابق", lang), "kind": "number"},
                                     {"key": "current", "label": _t("Current", "الحالي", lang), "kind": "number"},
                                     {"key": "change", "label": _t("Change", "التغير", lang), "kind": "number"}], "rows": rows})
        since = context.now() - timedelta(days=30)
        session = context.session()
        scope = department_scope(actor)
        changed = []
        for h, a in session.execute(select(AssetStatusHistory, Asset).join(Asset, Asset.id == AssetStatusHistory.asset_id)
                                    .where(AssetStatusHistory.changed_at >= since).order_by(AssetStatusHistory.changed_at.desc())):
            if scope is not None and a.department_id not in scope:
                continue
            if h.status_code in ("NOT_READY", "TEMP_NOT_READY", "UNDER_MAINTENANCE", "AWAITING_REPLACEMENT"):
                changed.append({"asset": a.code, "status": _status("ASSET", h.status_code, lang), "date": h.changed_at.date().isoformat(),
                                "department": _n(lk.ref_id(Department, a.department_id), lang)})
        sections.append({"kind": "table", "title": _t("Assets that became unavailable (30 days)", "الأصول التي أصبحت غير متاحة (30 يوماً)", lang),
                         "columns": [{"key": "asset", "label": _t("Asset", "الأصل", lang), "kind": "text"},
                                     {"key": "status", "label": _t("Status", "الحالة", lang), "kind": "text"},
                                     {"key": "department", "label": _t("Department", "الإدارة", lang), "kind": "text"},
                                     {"key": "date", "label": _t("Date", "التاريخ", lang), "kind": "date"}], "rows": changed})
        projects = [r for r in _projects(actor, lang) if (r["delay"] or 0) > 0]
        sections.append({"kind": "table", "title": _t("Delayed projects", "المشاريع المتأخرة", lang),
                         "columns": _columns("projects", ["code", "project", "department", "status", "forecast", "delay", "health"], lang),
                         "rows": _clean(projects)})
        new_risks = [r for r in _risks(actor, lang) if r["_level"] in ("CRITICAL", "HIGH") and r["_status"] != "CLOSED"]
        sections.append({"kind": "table", "title": _t("Critical and high risks", "المخاطر الحرجة والعالية", lang),
                         "columns": _columns("risks", ["code", "project", "risk", "score", "level", "owner", "due"], lang),
                         "rows": _clean(new_risks)})
        upcoming = [m for m in _milestones(actor, lang) if m["_status"] != "COMPLETED" and m["plannedEnd"]
                    and context.today().isoformat() <= (m["forecast"] or m["plannedEnd"]) <= (context.today() + timedelta(days=30)).isoformat()]
        sections.append({"kind": "table", "title": _t("Milestones in the next 30 days", "المراحل خلال 30 يوماً القادمة", lang),
                         "columns": _columns("milestones", ["project", "milestone", "owner", "plannedEnd", "forecast", "status"], lang),
                         "rows": _clean(upcoming)})
    elif kind == "decision":
        for p in operations_service.decision_support(actor)["panels"]:
            sections.append({"kind": "list", "title": f"{_t(*DECISION_PANELS.get(p['key'], (p['key'], p['key'])), lang)} ({p['count']})",
                             "basis": _t(p["basisEn"], p["basisAr"], lang),
                             "items": [_t(i["textEn"], i["textAr"], lang) + (f" — {_t(i['subEn'], i['subAr'], lang)}" if i["subEn"] else "")
                                       for i in p["items"]]})
    elif kind == "trend":
        metric = report["metric"]
        series = snapshot_service.series(metric, None, context.today() - timedelta(days=400))
        monthly = {}
        for point in series:
            monthly[point["date"][:7]] = point
        rows = [{"month": k, "value": v["value"]} for k, v in sorted(monthly.items())]
        sections.append({"kind": "bar", "title": _t(report["titleEn"], report["titleAr"], lang),
                         "items": [{"label": r["month"], "value": r["value"]} for r in rows]})
        sections.append({"kind": "table", "title": _t("Values", "القيم", lang),
                         "columns": [{"key": "month", "label": _t("Month", "الشهر", lang), "kind": "text"},
                                     {"key": "value", "label": _t("Value", "القيمة", lang), "kind": "number"}], "rows": rows})
    row_count = sum(len(s.get("rows", s.get("items", []))) for s in sections if s["kind"] in ("table", "list"))
    return {"key": report["key"], "titleEn": report["titleEn"], "titleAr": report["titleAr"], "header": header,
            "sections": sections, "rowCount": row_count}


def run_report(actor, key: str, lang: str = "EN", file_format: str = "SCREEN", log: bool = True) -> dict:
    require_permission(actor, PERM_REPORTS_VIEW)
    lang = lang if lang in LANGS else "EN"
    if key.startswith("template-"):
        result = run_template(actor, int(key.split("-", 1)[1]), lang)
    else:
        report = _cat().get(key)
        if report is None:
            raise NotFound(f"Report {key} was not found.")
        if not has_permission(actor, report["perm"]):
            raise Forbidden("Your role does not allow this report.")
        if report.get("special"):
            result = _special(actor, report, lang)
        else:
            result = run_definition(actor, {"dataset": report["dataset"], "group": report.get("group"),
                                             "where": report.get("where")}, lang, report["titleEn"], report["titleAr"], key)
    if log:
        log_run(actor, result, lang, file_format)
    return result


def log_run(actor, result: dict, lang: str, file_format: str, schedule_id: int | None = None, file_name: str | None = None):
    session = context.session()
    session.add(ReportRun(report_key=result["key"][:80], title=(result["titleEn"] or result["key"])[:200], schedule_id=schedule_id,
                          run_at=context.now(), run_by=actor.id, language=lang, file_format=file_format,
                          row_count=result.get("rowCount", 0), file_name=file_name))
    session.commit()


def run_history(actor, limit: int = 50) -> list[dict]:
    require_permission(actor, PERM_REPORTS_VIEW)
    from ..models import AppUser
    session = context.session()
    query = select(ReportRun).order_by(ReportRun.run_at.desc(), ReportRun.id.desc()).limit(limit)
    from ..security.auth import can_admin
    if not can_admin(actor):
        query = query.where(ReportRun.run_by == actor.id)
    return [{"id": sid(r.id), "key": r.report_key, "title": r.title, "runAt": iso_utc(r.run_at),
             "by": (session.get(AppUser, r.run_by) or AppUser(display_name="?")).display_name, "language": r.language,
             "format": r.file_format, "rows": r.row_count, "scheduled": r.schedule_id is not None, "fileName": r.file_name,
             "hasFile": bool(r.file_name and r.schedule_id is not None)}
            for r in session.scalars(query)]


# ---------------------------------------------------------------- custom builder -----------------------------------


def _check_definition(defn: dict) -> dict:
    if not isinstance(defn, dict):
        raise ValidationFailed.field("definition", "Must be an object.")
    allowed = {"dataset", "columns", "group", "filters", "sort", "desc", "chart"}
    unknown = set(defn) - allowed
    if unknown:
        raise ValidationFailed.field("definition", f"Unsupported key: {', '.join(sorted(unknown))}.")
    dataset = defn.get("dataset")
    if dataset not in DATASETS:
        raise ValidationFailed.field("dataset", "Unknown dataset.")
    keys = {f[0] for f in DATASETS[dataset][2]}
    columns = defn.get("columns")
    if columns is not None and (not isinstance(columns, list) or not columns or any(c not in keys for c in columns)):
        raise ValidationFailed.field("columns", "Choose at least one field of the dataset.")
    if defn.get("group") is not None and defn["group"] not in keys:
        raise ValidationFailed.field("group", "Unknown field.")
    filters = defn.get("filters") or {}
    if not isinstance(filters, dict) or any(k not in keys for k in filters):
        raise ValidationFailed.field("filters", "Unknown field.")
    if defn.get("chart") not in (None, "table", "bar"):
        raise ValidationFailed.field("chart", "Must be table or bar.")
    return defn


def run_custom(actor, definition: dict, lang: str) -> dict:
    require_permission(actor, PERM_REPORTS_BUILD)
    defn = _check_definition(definition)
    en, ar = _DATASET_NAMES[defn["dataset"]]
    return run_definition(actor, defn, lang, f"Custom report: {en}", f"تقرير مخصص: {ar}", "custom")


def template_dto(t: ReportTemplate) -> dict:
    return {"id": sid(t.id), "name": t.name, "shared": bool(t.is_shared), "ownerId": sid(t.owner_id),
            "definition": json.loads(t.definition_json), **record_meta(t)}


def list_templates(actor) -> list[dict]:
    require_permission(actor, PERM_REPORTS_VIEW)
    from sqlalchemy import or_
    rows = context.session().scalars(select(ReportTemplate).where(ReportTemplate.archived_at.is_(None),
                                                                  or_(ReportTemplate.owner_id == actor.id, ReportTemplate.is_shared == 1))
                                     .order_by(ReportTemplate.name))
    return [template_dto(t) for t in rows]


def save_template(actor, name: str, definition: dict, shared: bool, template_id: int | None = None, version=None) -> dict:
    require_permission(actor, PERM_REPORTS_BUILD)
    defn = _check_definition(definition)
    encoded = json.dumps(defn, ensure_ascii=False, sort_keys=True)
    if len(encoded) > 4000:
        raise ValidationFailed.field("definition", "The report definition is too long.")
    from . import crud
    if template_id is None:
        tpl = ReportTemplate(name=name, owner_id=actor.id, is_shared=1 if shared else 0, definition_json=encoded)
        crud.create(actor, tpl, PERM_REPORTS_BUILD)
    else:
        tpl = context.session().get(ReportTemplate, template_id)
        if tpl is None or tpl.owner_id != actor.id:
            raise NotFound("Template was not found.")
        crud.update(actor, tpl, {"name": name, "is_shared": 1 if shared else 0, "definition_json": encoded}, PERM_REPORTS_BUILD,
                    version, None, department_ids=(None,))
    return template_dto(tpl)


def run_template(actor, template_id: int, lang: str) -> dict:
    tpl = context.session().get(ReportTemplate, template_id)
    if tpl is None or tpl.archived_at is not None or (tpl.owner_id != actor.id and not tpl.is_shared):
        raise NotFound("Template was not found.")
    defn = json.loads(tpl.definition_json)
    return run_definition(actor, defn, lang, tpl.name, tpl.name, f"template-{tpl.id}")

