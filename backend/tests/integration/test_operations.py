"""Testing & evaluation, maintenance, AI capability levels, development potential, decision support."""
from __future__ import annotations


def _model_id(api, code):
    return next(m["id"] for m in api.json("/api/v1/models")["items"] if m["code"] == code)


def test_test_kpis_and_pass_rate(admin):
    k = admin.json("/api/v1/tests")["kpis"]
    assert k["total"] == 18 and k["passed"] == 7 and k["failed"] == 2 and k["conditional"] == 3
    assert k["passRate"] == round(100 * 7 / 12)


def test_failed_project_test_turns_the_testing_indicator_red(admin):
    prj = next(p for p in admin.json("/api/v1/projects")["items"] if p["code"] == "PRJ-011")
    testing = admin.json(f"/api/v1/projects/{prj['id']}")["indicators"]["TESTING"]
    assert testing["rag"] == "RED" and "TST-009" in testing["reasonEn"]


def test_ai_level_is_derived_with_a_trace(admin):
    ai = admin.json(f"/api/v1/models/{_model_id(admin, 'M003')}/ai")
    assert ai["level"] == 4
    l5 = ai["trace"][4]
    assert not l5["met"] and set(l5["missing"]) == {"SWARM_COORDINATION", "DECISION_SUPPORT"}


def test_changing_ai_functions_moves_the_level_and_is_audited(capability, admin):
    model_id = _model_id(admin, "M007")
    assert admin.json(f"/api/v1/models/{model_id}/ai")["level"] == 1
    res = capability.put(f"/api/v1/models/{model_id}/ai", json={
        "technologies": ["AUTONOMOUS_NAVIGATION", "OBJECT_DETECTION", "COMPUTER_VISION"], "reason": "Retrofit"})
    assert res.status_code == 200 and res.get_json()["level"] == 2
    events = admin.json(f"/api/v1/history/CAPABILITY_MODEL/{model_id}")["items"]
    assert events[0]["reason"] == "Retrofit"
    assert capability.put(f"/api/v1/models/{model_id}/ai", json={"technologies": ["NOPE"]}).status_code == 400


def test_maintenance_kpis_and_overdue(admin):
    d = admin.json("/api/v1/maintenance")
    assert d["kpis"]["active"] == 8 and d["kpis"]["overdue"] >= 1
    assert all(m["overdue"] == (m["daysOverdue"] > 0) for m in d["items"])
    assert d["readinessByDepartment"]


def test_maintenance_writes_follow_role_and_department(app, admin, viewer):
    from tests.conftest import Api
    maint = Api(app, "mock.maint")
    asset_id = admin.json("/api/v1/assets?size=1")["items"][0]["id"]
    body = {"code": "MNT-099", "assetId": asset_id, "maintType": "INSPECTION", "titleEn": "Check", "titleAr": "فحص",
            "statusCode": "PLANNED", "startDate": "2026-10-10"}
    assert viewer.post("/api/v1/maintenance", json=body).status_code == 403
    res = maint.post("/api/v1/maintenance", json=body)
    assert res.status_code == 201, res.get_json()


def test_decision_support_panels_state_their_basis(admin):
    panels = admin.json("/api/v1/decision-support")["panels"]
    assert len(panels) == 11
    assert all(p["basisEn"] and p["basisAr"] for p in panels)
    by_key = {p["key"]: p for p in panels}
    assert by_key["criticalGaps"]["count"] == 3


def test_department_head_sees_only_its_tests_and_maintenance(head):
    assert all(e["department"]["code"] == "G2" for e in head.json("/api/v1/tests")["items"])
    assert all(m["department"]["code"] == "G2" for m in head.json("/api/v1/maintenance")["items"])


def test_search_covers_tests_and_maintenance(admin):
    data = admin.json("/api/v1/search?q=TST-009")
    assert data["tests"] and data["tests"][0]["code"] == "TST-009"
    assert admin.json("/api/v1/search?q=MNT-001")["maintenance"]


def _units(api) -> dict:
    return {u["code"]: u for u in api.json("/api/v1/lookups")["units"]}


def test_directorate_and_its_sections_are_reference_data(admin):
    units = _units(admin)
    directorate = units["CAP-DEV-DIR"]
    assert directorate["parentId"] is None and directorate["nameAr"] == "مديرية تطوير القدرات"
    assert {units["SEC-SYS"]["nameAr"], units["CAP-DEV"]["nameAr"]} == {"شعبة الأنظمة الأمنية", "شعبة تطوير القدرات"}
    assert units["SEC-SYS"]["parentId"] == units["CAP-DEV"]["parentId"] == directorate["id"]


def test_tests_filter_by_directorate_or_section(admin):
    units = _units(admin)
    every = admin.json("/api/v1/tests")
    by_directorate = admin.json(f"/api/v1/tests?unit={units['CAP-DEV-DIR']['id']}")
    assert by_directorate["kpis"]["total"] == every["kpis"]["total"] == 18   # the directorate = all its sections
    security = admin.json(f"/api/v1/tests?unit={units['SEC-SYS']['id']}")
    development = admin.json(f"/api/v1/tests?unit={units['CAP-DEV']['id']}")
    assert {e["unit"]["code"] for e in security["items"]} == {"SEC-SYS"}
    assert {e["unit"]["code"] for e in development["items"]} == {"CAP-DEV"}
    assert security["kpis"]["total"] == len(security["items"]) == 8
    assert development["kpis"]["total"] == len(development["items"]) == 10


def test_a_test_records_its_conducting_section(admin):
    units = _units(admin)
    test = next(e for e in admin.json("/api/v1/tests")["items"] if e["code"] == "TST-002")
    assert test["unit"]["code"] == "SEC-SYS"
    res = admin.patch(f"/api/v1/tests/{test['id']}", json={"unitId": units["CAP-DEV"]["id"], "version": test["version"],
                                                           "reason": "Moved to the development section"})
    assert res.status_code == 200 and res.get_json()["unit"]["code"] == "CAP-DEV"
    events = admin.json(f"/api/v1/history/TEST_EVENT/{test['id']}")["items"]
    assert events[0]["reason"] == "Moved to the development section"
    bad = admin.patch(f"/api/v1/tests/{test['id']}", json={"unitId": 999999, "version": res.get_json()["version"]})
    assert bad.status_code == 400


def test_units_have_two_levels_only(admin):
    units = _units(admin)
    # a new section under the directorate is fine
    res = admin.post("/api/v1/admin/lists/units", json={"code": "C-UAS", "nameEn": "Counter-UAS Section",
                                                        "nameAr": "شعبة مكافحة الطائرات", "parentId": units["CAP-DEV-DIR"]["id"]})
    assert res.status_code == 201, res.get_json()
    # a section cannot have sections of its own
    deeper = admin.post("/api/v1/admin/lists/units", json={"code": "C-UAS-2", "nameEn": "Team", "nameAr": "فريق",
                                                           "parentId": units["SEC-SYS"]["id"]})
    assert deeper.status_code == 400
    # a directorate with sections cannot move under another directorate
    other = admin.post("/api/v1/admin/lists/units", json={"code": "OTHER-DIR", "nameEn": "Other Directorate",
                                                          "nameAr": "مديرية أخرى"}).get_json()
    move = admin.patch(f"/api/v1/admin/lists/units/{units['CAP-DEV-DIR']['id']}",
                       json={"parentId": other["id"], "version": units["CAP-DEV-DIR"]["version"]})
    assert move.status_code == 400
