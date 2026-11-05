"""The application on a real Oracle database, as the restricted runtime account: schema check, bootstrap (roles,
first administrator, reference lists), every kind of write, the computed views, reports and exports, and the
database-side protections (append-only audit, no DELETE on business tables)."""
from __future__ import annotations

import io
import zipfile

import pytest

from tests.conftest import Api

pytestmark = pytest.mark.oracle
ADMIN_PASSWORD = "Oracle-Test-Admin-1"


@pytest.fixture(scope="module")
def admin(oracle_app):
    from app.core.database import write_intent
    from app.seed.demo_seeder import seed_reference, seed_roles
    from app.services import user_service

    with oracle_app.test_request_context("/"):
        with write_intent():
            seed_roles()
            from app.services import context
            context.session().commit()
            admin = user_service.create_user("u10001", "Oracle Test Admin", "SYS_ADMIN", ADMIN_PASSWORD)
            counts = seed_reference(admin)
        assert counts["departments"] == 4 and counts["statuses"] > 40
    return Api(oracle_app, "u10001", ADMIN_PASSWORD)


def _id(api, path, key, value):
    return next(e["id"] for e in api.json(path)[key] if e.get("code") == value)


def test_reference_lists_and_lookups(admin):
    lookups = admin.json("/api/v1/lookups")
    assert len(lookups["departments"]) == 4 and len(lookups["categories"]) == 4
    assert len(lookups["projectTypes"]) == 6 and lookups["statuses"]["ASSET"]


def test_capability_records_round_trip(admin):
    lookups = admin.json("/api/v1/lookups")
    uav = next(c["id"] for c in lookups["categories"] if c["code"] == "UAV")
    g2 = next(d["id"] for d in lookups["departments"] if d["code"] == "G2")
    model = admin.post("/api/v1/models", json={"code": "OM1", "nameEn": "Oracle Falcon", "nameAr": "فالكون أوراكل",
                                               "categoryId": uav, "unitCost": 1250000.5, "specs": {"endurance": 12}})
    assert model.status_code == 201, model.get_json()
    model_id = model.get_json()["id"]
    req = admin.post("/api/v1/requirements", json={"code": "ORQ1", "nameEn": "Oracle requirement", "nameAr": "متطلب",
                                                   "departmentId": g2, "categoryId": uav, "requiredQty": 3,
                                                   "priority": "CRITICAL", "modelIds": [model_id],
                                                   "targetDate": "2027-06-30"})
    assert req.status_code == 201, req.get_json()
    for code, status in (("OA-1", "READY"), ("OA-2", "UNDER_MAINTENANCE"), ("OA-3", "UNDER_ACQUISITION")):
        res = admin.post("/api/v1/assets", json={"code": code, "modelId": model_id, "departmentId": g2,
                                                 "statusCode": status, "readinessOperational": 90,
                                                 "acquisitionDate": "2025-03-01", "serialNumber": f"SN-{code}"})
        assert res.status_code == 201, res.get_json()
    r = admin.json(f"/api/v1/requirements/{req.get_json()['id']}")
    assert r["available"] == 2 and r["gap"] == 1 and r["pipeline"]["UNDER_ACQUISITION"] == 1
    asset = admin.json("/api/v1/assets?q=OA-1")["items"][0]
    upd = admin.patch(f"/api/v1/assets/{asset['id']}", json={"statusCode": "NOT_READY", "version": asset["version"],
                                                             "reason": "Oracle test"})
    assert upd.status_code == 200 and upd.get_json()["statusHistory"][0]["status"] == "NOT_READY"
    stale = admin.patch(f"/api/v1/assets/{asset['id']}", json={"statusCode": "READY", "version": asset["version"]})
    assert stale.status_code == 409
    history = admin.json(f"/api/v1/history/ASSET/{asset['id']}")["items"]
    assert history[0]["reason"] == "Oracle test" and history[0]["occurredAt"].endswith("Z")


def test_projects_operations_documents(admin):
    lookups = admin.json("/api/v1/lookups")
    ptype = next(t for t in lookups["projectTypes"] if t["code"] == "NEW_ACQUISITION")
    uav = next(c["id"] for c in lookups["categories"] if c["code"] == "UAV")
    g2 = next(d["id"] for d in lookups["departments"] if d["code"] == "G2")
    prj = admin.post("/api/v1/projects", json={"code": "OPRJ-1", "nameEn": "Oracle project", "nameAr": "مشروع أوراكل",
                                               "projectTypeId": ptype["id"], "departmentId": g2, "categoryId": uav,
                                               "statusCode": "CONTRACTING", "budget": 1000000, "actualSpend": 900000,
                                               "committed": 300000, "startDate": "2026-01-01",
                                               "targetEndDate": "2026-06-30", "forecastEndDate": "2026-09-30"})
    assert prj.status_code == 201, prj.get_json()
    p = prj.get_json()
    assert p["indicators"]["BUDGET"]["rag"] == "RED" and p["delayDays"] > 0
    assert admin.post("/api/v1/risks", json={"code": "ORSK-1", "projectId": p["id"], "titleEn": "Risk", "titleAr": "خطر",
                                             "category": "TECHNICAL", "probability": 5, "impact": 4,
                                             "statusCode": "OPEN"}).status_code == 201
    assert admin.post("/api/v1/milestones", json={"projectId": p["id"], "nameEn": "Delivery", "nameAr": "التسليم",
                                                  "plannedStartDate": "2026-05-01", "plannedEndDate": "2026-06-01",
                                                  "statusCode": "IN_PROGRESS", "isMajor": True}).status_code == 201
    model_id = admin.json("/api/v1/models?q=OM1")["items"][0]["id"]
    assert admin.post("/api/v1/tests", json={"code": "OTST-1", "titleEn": "Oracle flight", "titleAr": "طيران",
                                             "modelId": model_id, "departmentId": g2, "testType": "INTERNAL",
                                             "testDate": "2026-04-01", "statusCode": "FAILED", "score": 40,
                                             "projectId": p["id"]}).status_code == 201
    assert admin.json(f"/api/v1/projects/{p['id']}")["indicators"]["TESTING"]["rag"] == "RED"
    asset_id = admin.json("/api/v1/assets?q=OA-2")["items"][0]["id"]
    assert admin.post("/api/v1/maintenance", json={"code": "OMNT-1", "assetId": asset_id, "maintType": "CORRECTIVE",
                                                   "titleEn": "Fix", "titleAr": "إصلاح", "statusCode": "AWAITING_PARTS",
                                                   "startDate": "2026-01-10", "expectedEndDate": "2026-02-01",
                                                   "partsShortage": True}).status_code == 201
    assert admin.put(f"/api/v1/models/{model_id}/ai", json={"technologies": ["COMPUTER_VISION", "OBJECT_DETECTION",
                                                                              "OBJECT_TRACKING"]}).get_json()["level"] == 2
    doc = admin.post("/api/v1/documents", json={"code": "ODOC-1", "titleEn": "Spec", "titleAr": "مواصفات",
                                                "docType": "SPECIFICATION", "entityType": "PROJECT", "entityId": p["id"]})
    assert doc.status_code == 201, doc.get_json()
    up = admin.client.post(f"/api/v1/documents/{doc.get_json()['id']}/versions",
                           data={"file": (io.BytesIO(b"%PDF-1.4 oracle"), "spec.pdf"), "note": "v1"},
                           content_type="multipart/form-data", headers={"X-CSRF-Token": admin.csrf})
    assert up.status_code == 201 and up.get_json()["currentVersion"] == 1
    assert admin.get(f"/api/v1/documents/{doc.get_json()['id']}/file").data.startswith(b"%PDF")


def test_views_alerts_and_settings(admin):
    d = admin.json("/api/v1/dashboard")
    assert d["inventory"]["assets"]["value"] == 3
    assert admin.json("/api/v1/gaps")["register"]
    alerts = admin.json("/api/v1/alerts")
    assert {"PROJECT_DELAYED", "BUDGET_OVERRUN", "SPARE_PARTS_SHORTAGE"} <= {a["type"] for a in alerts["items"]}
    assert admin.post("/api/v1/alerts/acknowledge", json={"keys": [alerts["items"][0]["key"]]}).status_code == 200
    rule = next(s for s in admin.json("/api/v1/settings")["items"] if s["key"] == "health.schedule")
    assert admin.put("/api/v1/settings/health.schedule", json={"value": {"amber_days": 2, "red_days": 20},
                                                               "version": rule["version"]}).status_code == 200
    roles = {r["code"]: r for r in admin.json("/api/v1/admin/roles")["items"]}
    assert admin.patch(f"/api/v1/admin/roles/{roles['VIEWER']['id']}", json={"permissions": ["view", "export"],
                                                                             "version": roles["VIEWER"]["version"]}).status_code == 200
    view = admin.post("/api/v1/saved-views", json={"page": "registry", "name": "x", "filters": {"q": "OA"}})
    assert admin.delete(f"/api/v1/saved-views/{view.get_json()['id']}").status_code == 204
    assert admin.json("/api/v1/search?q=Oracle")["projects"]


def test_reports_and_exports(admin):
    for item in admin.json("/api/v1/reports")["items"]:
        res = admin.get(f"/api/v1/reports/{item['key']}?lang=AR")
        assert res.status_code == 200, (item["key"], res.get_json())
    for fmt in ("XLSX", "PPTX"):
        data = admin.get(f"/api/v1/reports/executive-summary/export?format={fmt}&lang=AR").data
        assert zipfile.ZipFile(io.BytesIO(data)).testzip() is None
    assert admin.post("/api/v1/report-schedules", json={"name": "Daily", "reportKey": "assets-register",
                                                        "frequency": "DAILY", "language": "EN", "format": "CSV",
                                                        "runTime": "06:00", "outputFolder": "Oracle"}).status_code == 201


def test_audit_is_append_only_and_records_are_never_deleted(oracle_app, admin):
    from sqlalchemy import text
    from sqlalchemy.exc import DatabaseError

    from app.extensions import db
    with oracle_app.app_context():
        session = db.new_session()
        try:
            for statement in ("UPDATE audit_event SET reason = 'x'", "DELETE FROM audit_event", "DELETE FROM asset",
                              "DELETE FROM project"):
                with pytest.raises(DatabaseError):
                    session.execute(text(statement))
                session.rollback()
        finally:
            session.close()
