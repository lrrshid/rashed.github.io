"""Reports: catalogue, every report runs in both languages, permissions inherited, exports, builder, schedules."""
from __future__ import annotations

import io
import zipfile


def test_catalogue_has_about_130_reports(admin):
    data = admin.json("/api/v1/reports")
    assert data["total"] >= 110
    assert {c["key"] for c in data["categories"]} >= {"executive", "assets", "projects", "risks", "maintenance"}


def test_every_report_runs_in_english_and_arabic(admin):
    for item in admin.json("/api/v1/reports")["items"]:
        for lang in ("EN", "AR"):
            res = admin.get(f"/api/v1/reports/{item['key']}?lang={lang}")
            assert res.status_code == 200, (item["key"], lang, res.get_json())
            body = res.get_json()
            assert body["header"]["classification"] and body["header"]["generatedBy"]


def test_reports_inherit_department_scope(head, admin):
    mine = head.json("/api/v1/reports/assets-register")["sections"][1]["rows"]
    everyone = admin.json("/api/v1/reports/assets-register")["sections"][1]["rows"]
    assert 0 < len(mine) < len(everyone)
    assert {r["department"] for r in mine} == {"Group 2"}


def test_executive_reports_need_the_executive_permission(app):
    from tests.conftest import Api
    tester = Api(app, "mock.test")  # TESTING role: reports.view but not reports.exec
    keys = {r["key"] for r in tester.json("/api/v1/reports")["items"]}
    assert "executive-summary" not in keys and "assets-register" in keys
    assert tester.get("/api/v1/reports/executive-summary").status_code == 403


def test_exports_are_valid_files_and_logged(admin):
    for fmt in ("XLSX", "PPTX"):
        res = admin.get(f"/api/v1/reports/leadership-monthly/export?format={fmt}&lang=AR")
        assert res.status_code == 200
        names = zipfile.ZipFile(io.BytesIO(res.data)).namelist()
        assert ("xl/workbook.xml" in names) if fmt == "XLSX" else ("ppt/presentation.xml" in names)
    csv = admin.get("/api/v1/reports/assets-register/export?format=CSV")
    assert csv.status_code == 200 and csv.data.decode("utf-8-sig").startswith("Asset ID")
    formats = {r["format"] for r in admin.json("/api/v1/reports/history")["items"]}
    assert {"XLSX", "PPTX", "CSV"} <= formats


def test_export_needs_the_export_permission(viewer):
    assert viewer.get("/api/v1/reports/assets-register/export?format=CSV").status_code == 403


def test_custom_builder_groups_and_filters(admin):
    res = admin.post("/api/v1/reports/custom", json={"definition": {"dataset": "assets", "group": "department",
                                                                    "filters": {"category": "UAV"}}, "lang": "EN"})
    assert res.status_code == 200, res.get_json()
    table = next(s for s in res.get_json()["sections"] if s["kind"] == "table")
    assert sum(r["count"] for r in table["rows"]) == res.get_json()["rowCount"]
    bad = admin.post("/api/v1/reports/custom", json={"definition": {"dataset": "assets", "group": "password_hash"}})
    assert bad.status_code == 400


def test_templates_and_schedules(admin):
    tpl = admin.post("/api/v1/report-templates", json={"name": "UAV by site", "definition": {"dataset": "assets", "group": "site",
                                                                                                "filters": {"category": "UAV"}}})
    assert tpl.status_code == 201
    run = admin.get(f"/api/v1/reports/template-{tpl.get_json()['id']}")
    assert run.status_code == 200
    sched = admin.post("/api/v1/report-schedules", json={"name": "Weekly risks", "reportKey": "risks-critical", "frequency": "WEEKLY",
                                                         "language": "AR", "format": "XLSX", "sendTime": "07:30",
                                                         "recipients": ["pmo@example.gov"]})
    assert sched.status_code == 201, sched.get_json()
    bad = admin.post("/api/v1/report-schedules", json={"name": "x", "reportKey": "risks-critical", "frequency": "WEEKLY",
                                                       "language": "AR", "format": "XLSX", "sendTime": "25:00", "recipients": ["nope"]})
    assert bad.status_code == 400


def test_due_schedules_produce_files(app, tmp_path):
    from datetime import timedelta

    from app.services import context, schedule_service
    from app.core.database import write_intent
    with app.test_request_context("/"):
        with write_intent():
            produced = schedule_service.run_due(context.today() + timedelta(days=40), out_dir=tmp_path)
    assert len(produced) == 3
    assert all((tmp_path / p["file"].split("\\")[-1].split("/")[-1]).exists() for p in produced)
