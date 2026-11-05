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
                                                         "language": "AR", "format": "XLSX", "runTime": "07:30",
                                                         "outputFolder": "مكتب المشاريع"})
    assert sched.status_code == 201, sched.get_json()
    for bad_folder in ("../escape", "a/b", "..", ""):
        bad = admin.post("/api/v1/report-schedules", json={"name": "x", "reportKey": "risks-critical", "frequency": "WEEKLY",
                                                           "language": "AR", "format": "XLSX", "runTime": "07:30",
                                                           "outputFolder": bad_folder})
        assert bad.status_code == 400, bad_folder
    bad_time = admin.post("/api/v1/report-schedules", json={"name": "x", "reportKey": "risks-critical", "frequency": "WEEKLY",
                                                            "language": "AR", "format": "XLSX", "runTime": "25:00",
                                                            "outputFolder": "Reports"})
    assert bad_time.status_code == 400


def test_due_schedules_write_files_to_the_reports_folder_and_can_be_downloaded(app, admin, tmp_path):
    from datetime import timedelta
    from pathlib import Path

    from app.core.database import write_intent
    from app.services import context, schedule_service
    app.config["SETTINGS"].reports_dir = str(tmp_path)
    with app.test_request_context("/"):
        with write_intent():
            produced = schedule_service.run_due(context.today() + timedelta(days=40))
    assert len(produced) == 3
    assert all(Path(p["file"]).is_file() and tmp_path in Path(p["file"]).parents for p in produced)
    assert {Path(p["file"]).parents[1].name for p in produced} == {"Command office", "Project office", "Maintenance"}
    runs = [r for r in admin.json("/api/v1/reports/history")["items"] if r["hasFile"]]
    assert len(runs) == 3
    res = admin.get(f"/api/v1/reports/history/{runs[0]['id']}/file")
    assert res.status_code == 200 and len(res.data) > 100
    viewer_runs = admin.get("/api/v1/reports/history/999999/file")
    assert viewer_runs.status_code == 404


def test_decision_support_report_names_its_panels(admin):
    for lang, word in (("EN", "Critical capability gaps"), ("AR", "فجوات القدرات الحرجة")):
        titles = [s["title"] for s in admin.json(f"/api/v1/reports/decision-support?lang={lang}")["sections"]]
        assert any(t.startswith(word) for t in titles), titles
        assert not any(t.startswith("criticalGaps") for t in titles)


def test_arabic_output_shows_labels_and_dd_mm_yyyy_not_raw_codes(admin):
    import re
    leadership = admin.json("/api/v1/reports/leadership-monthly?lang=AR")
    risks = next(s for s in leadership["sections"] if s.get("kind") == "table" and any(c["key"] == "level" for c in s["columns"]))
    assert risks["rows"] and {r["level"] for r in risks["rows"]} <= {"حرجة", "عالية"}
    iso = re.compile(r"\d{4}-\d{2}-\d{2}")
    for panel in admin.json("/api/v1/decision-support")["panels"]:
        for item in panel["items"]:
            assert not iso.search(item["subEn"] + item["subAr"]), item
            assert item["subAr"] not in ("CRITICAL", "HIGH"), item
    for alert in admin.json("/api/v1/alerts")["items"]:
        assert not iso.search(alert["textEn"] + alert["textAr"]), alert
