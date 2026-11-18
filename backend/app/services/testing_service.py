"""Testing & evaluation: internal and external tests, results by model, pass rate, history timeline; and the
project "testing" health indicator (project_health.py) from each project's latest completed test."""
from __future__ import annotations

from collections import Counter, defaultdict

from sqlalchemy import select

from ..exceptions import ValidationFailed
from ..models import Asset, CapabilityModel, Department, OrgUnit, Project, Site, TestEvent
from ..schemas.dto import record_meta, sid
from ..security.auth import ALL_DEPARTMENTS, PERM_EDIT_TESTING, department_scope
from . import context, crud, lookup_service as lk

DONE = ("PASSED", "CONDITIONAL", "FAILED")


def _scoped(actor, query):
    scope = department_scope(actor)
    if scope is not ALL_DEPARTMENTS:
        query = query.where(TestEvent.department_id.in_(sorted(scope) or [-1]))
    return query


def test_dto(e: TestEvent) -> dict:
    project = context.session().get(Project, e.project_id) if e.project_id else None
    asset = context.session().get(Asset, e.asset_id) if e.asset_id else None
    return {"id": sid(e.id), "code": e.code, "titleEn": e.title_en, "titleAr": e.title_ar,
            "model": lk.ref_id(CapabilityModel, e.model_id),
            "asset": {"id": sid(asset.id), "code": asset.code} if asset else None,
            "project": {"id": sid(project.id), "code": project.code, "nameEn": project.name_en, "nameAr": project.name_ar}
            if project else None,
            "department": lk.ref_id(Department, e.department_id), "site": lk.ref_id(Site, e.site_id),
            "unit": lk.ref_id(OrgUnit, e.unit_id),
            "testType": e.test_type, "testDate": e.test_date.isoformat(), "status": e.status_code, "score": e.score,
            "resultEn": e.result_en, "resultAr": e.result_ar, **record_meta(e)}


def unit_and_sections(unit_ids: list[int]) -> list[int]:
    """The units asked for plus their sections: filtering by a directorate lists the tests of all its sections."""
    children = context.session().scalars(select(OrgUnit.id).where(OrgUnit.parent_id.in_(unit_ids)))
    return sorted(set(unit_ids) | set(children))


def list_tests(actor, f: dict) -> dict:
    query = _scoped(actor, select(TestEvent).where(TestEvent.archived_at.is_(None)))
    for key, column in (("model", TestEvent.model_id), ("project", TestEvent.project_id),
                        ("department", TestEvent.department_id), ("asset", TestEvent.asset_id)):
        if f.get(key):
            query = query.where(column.in_(f[key]))
    if f.get("unit"):
        query = query.where(TestEvent.unit_id.in_(unit_and_sections(f["unit"])))
    if f.get("status"):
        query = query.where(TestEvent.status_code.in_(f["status"]))
    if f.get("type"):
        query = query.where(TestEvent.test_type == f["type"])
    rows = list(context.session().scalars(query.order_by(TestEvent.test_date.desc(), TestEvent.code)))
    today = context.today()
    status = Counter(e.status_code for e in rows)
    done = sum(status[s] for s in DONE)
    by_model = defaultdict(Counter)
    for e in rows:
        if e.status_code in DONE:
            by_model[e.model_id][e.status_code] += 1
    return {
        "items": [test_dto(e) for e in rows],
        "kpis": {"total": len(rows), "internal": sum(1 for e in rows if e.test_type == "INTERNAL"),
                 "external": sum(1 for e in rows if e.test_type == "EXTERNAL"),
                 "planned": status["PLANNED"], "inProgress": status["IN_PROGRESS"] + status["AWAITING_RESULT"],
                 "passed": status["PASSED"], "conditional": status["CONDITIONAL"], "failed": status["FAILED"],
                 "upcoming90": sum(1 for e in rows if e.status_code == "PLANNED" and 0 <= (e.test_date - today).days <= 90),
                 "passRate": round(100 * status["PASSED"] / done) if done else None},
        "byModel": [{"model": lk.ref_id(CapabilityModel, m), **{s: c.get(s, 0) for s in DONE}}
                    for m, c in sorted(by_model.items(), key=lambda kv: -sum(kv[1].values()))],
    }


def project_test_health(project_ids: list[int] | None) -> dict:
    """project id -> (rag, reason EN, reason AR) from the project's latest completed test."""
    query = select(TestEvent).where(TestEvent.archived_at.is_(None), TestEvent.project_id.is_not(None),
                                    TestEvent.status_code.in_(DONE))
    if project_ids is not None:
        query = query.where(TestEvent.project_id.in_(project_ids or [-1]))
    latest = {}
    for e in context.session().scalars(query.order_by(TestEvent.test_date)):
        latest[e.project_id] = e
    out = {}
    for pid, e in latest.items():
        rag = {"PASSED": "GREEN", "CONDITIONAL": "AMBER", "FAILED": "RED"}[e.status_code]
        word_en = {"PASSED": "passed", "CONDITIONAL": "passed with conditions", "FAILED": "failed"}[e.status_code]
        word_ar = {"PASSED": "ناجح", "CONDITIONAL": "نجاح مشروط", "FAILED": "غير ناجح"}[e.status_code]
        out[pid] = (rag, f"{e.code} {e.title_en}: {word_en}" + (f" ({e.result_en})" if e.result_en else ""),
                    f"{e.code} {e.title_ar}: {word_ar}" + (f" ({e.result_ar})" if e.result_ar else ""))
    return out


_FIELDS = ("title_en", "title_ar", "model_id", "asset_id", "project_id", "department_id", "site_id", "unit_id",
           "test_type", "test_date", "status_code", "score", "result_en", "result_ar")


def _validate(values: dict, current: TestEvent | None = None) -> None:
    if "model_id" in values:
        crud.check_ref(CapabilityModel, values["model_id"], "modelId", "Model", True)
    if "department_id" in values:
        crud.check_ref(Department, values["department_id"], "departmentId", "Department",
                       current is not None and current.department_id == values["department_id"])
    if values.get("asset_id"):
        asset = crud.check_ref(Asset, values["asset_id"], "assetId", "Asset", True)
        model_id = values.get("model_id", current.model_id if current else None)
        if asset.model_id != model_id:
            raise ValidationFailed.field("assetId", "The asset is not of the tested model.")
    if values.get("project_id"):
        crud.check_ref(Project, values["project_id"], "projectId", "Project", True)
    if values.get("site_id"):
        crud.check_ref(Site, values["site_id"], "siteId", "Site", True)
    if values.get("unit_id"):
        crud.check_ref(OrgUnit, values["unit_id"], "unitId", "Unit",
                       current is not None and current.unit_id == values["unit_id"])
    if "status_code" in values:
        crud.check_status("TEST", values["status_code"], "status", current.status_code if current else None)


def save_test(actor, data, test_id: int | None = None) -> dict:
    if test_id is None:
        values = {k: getattr(data, k) for k in _FIELDS}
        crud.check_unique_code(TestEvent, data.code)
        _validate(values)
        e = TestEvent(code=data.code, **values)
        crud.create(actor, e, PERM_EDIT_TESTING, values["department_id"])
    else:
        e = crud.load(TestEvent, test_id, actor, "Test", for_update=True)
        changes = {k: v for k, v in data.changes().items() if k in _FIELDS}
        _validate(changes, e)
        crud.update(actor, e, changes, PERM_EDIT_TESTING, data.version, data.reason,
                    department_ids=(e.department_id, changes.get("department_id", e.department_id)))
    return test_dto(e)
