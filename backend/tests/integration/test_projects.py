"""Projects: portfolio KPIs, health indicators with reasons, milestones, risks, issues, scope and permissions."""
from __future__ import annotations


def _project(api, code):
    return next(p for p in api.json("/api/v1/projects")["items"] if p["code"] == code)


def test_portfolio_kpis(admin):
    k = admin.json("/api/v1/projects")["kpis"]
    assert k["total"] == 14 and k["active"] == 13 and k["completed"] == 1 and k["delayed"] == 7


def test_views_filter_the_list(admin):
    delayed = admin.json("/api/v1/projects?view=DELAYED")["items"]
    assert len(delayed) == 7 and all(p["delayDays"] > 0 for p in delayed)


def test_six_indicators_each_state_a_reason(admin):
    p = admin.json(f"/api/v1/projects/{_project(admin, 'PRJ-006')['id']}")
    assert set(p["indicators"]) == {"SCHEDULE", "BUDGET", "SCOPE", "TESTING", "RISKS", "PROCUREMENT"}
    assert all(ind["reasonEn"] and ind["reasonAr"] for ind in p["indicators"].values())
    assert p["indicators"]["SCHEDULE"]["rag"] == "AMBER" and p["delayDays"] == 14
    assert p["indicators"]["RISKS"]["rag"] == "RED" and p["health"] == "RED"
    assert p["workflow"] and any(s["state"] == "CURRENT" for s in p["workflow"])


def test_forecast_slip_turns_schedule_red_and_is_audited(admin):
    summary = _project(admin, "PRJ-006")
    p = admin.json(f"/api/v1/projects/{summary['id']}")
    res = admin.patch(f"/api/v1/projects/{p['id']}", json={"forecastEndDate": "2027-03-01", "version": p["version"],
                                                           "reason": "Supplier delay"})
    assert res.status_code == 200, res.get_json()
    assert res.get_json()["indicators"]["SCHEDULE"]["rag"] == "RED"
    history = admin.json(f"/api/v1/history/PROJECT/{p['id']}")["items"]
    assert history[0]["reason"] == "Supplier delay"


def test_health_note_is_recorded_with_its_reason(pm, admin):
    pid = _project(admin, "PRJ-002")["id"]
    res = pm.put(f"/api/v1/projects/{pid}/health/SCOPE", json={"rag": "RED", "reasonEn": "Scope doubled",
                                                              "reasonAr": "تضاعف النطاق"})
    assert res.status_code == 200, res.get_json()
    assert res.get_json()["indicators"]["SCOPE"] == {"rag": "RED", "reasonEn": "Scope doubled", "reasonAr": "تضاعف النطاق"}
    assert pm.put(f"/api/v1/projects/{pid}/health/BUDGET", json={"rag": "RED"}).status_code == 404


def test_risk_score_level_and_matrix(pm, admin):
    pid = _project(admin, "PRJ-002")["id"]
    res = pm.post("/api/v1/risks", json={"code": "RSK-099", "projectId": pid, "titleEn": "Test risk",
                                         "titleAr": "خطر تجريبي", "category": "TECHNICAL", "probability": 5,
                                         "impact": 4, "statusCode": "OPEN"})
    assert res.status_code == 201, res.get_json()
    assert res.get_json()["score"] == 20 and res.get_json()["level"] == "CRITICAL"
    data = admin.json("/api/v1/risks")
    assert any(c["probability"] == 5 and c["impact"] == 4 for c in data["matrix"])


def test_issue_and_milestone_writes_need_the_permissions(viewer, admin):
    pid = _project(admin, "PRJ-002")["id"]
    assert viewer.post("/api/v1/issues", json={"code": "ISS-099", "projectId": pid, "titleEn": "x issue",
                                               "titleAr": "مشكلة", "severity": "LOW", "statusCode": "OPEN"}).status_code == 403
    res = admin.post("/api/v1/milestones", json={"projectId": pid, "nameEn": "Extra test", "nameAr": "اختبار إضافي",
                                                 "plannedStartDate": "2026-11-01", "plannedEndDate": "2026-10-01",
                                                 "statusCode": "NOT_STARTED"})
    assert res.status_code == 400  # end before start


def test_department_head_sees_only_its_projects(head):
    items = head.json("/api/v1/projects")["items"]
    assert items and all(p["department"]["code"] == "G2" for p in items)
    risks = head.json("/api/v1/risks")["items"]
    assert all(r["project"]["department"]["code"] == "G2" for r in risks)


def test_timeline_lists_major_milestones(admin):
    data = admin.json("/api/v1/timeline")
    assert data["items"] and any(p["milestones"] for p in data["items"])
