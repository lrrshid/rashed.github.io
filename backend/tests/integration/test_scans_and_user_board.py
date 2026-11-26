"""Golden-sample trials, attached scans in fixed slots (tests, maintenance, golden samples), the culture library and
the reason a capability entered maintenance. (The user board became user tracking: test_user_tracking.py.)"""
from __future__ import annotations

import io

from tests.conftest import Api

PDF = b"%PDF-1.4 scanned page"


def _attach(api, entity_type, entity_id, doc_type, data=PDF, name="scan.pdf"):
    form = {"entityType": entity_type, "entityId": str(entity_id), "docType": doc_type, "file": (io.BytesIO(data), name)}
    return api.client.post("/api/v1/attachments", data=form, content_type="multipart/form-data",
                           headers={"X-CSRF-Token": api.csrf})


def _model_id(api, code="M001"):
    return next(m["id"] for m in api.json("/api/v1/models")["items"] if m["code"] == code)


def _new_trial(api, code="GS-101"):
    res = api.post("/api/v1/golden-samples", json={
        "code": code, "titleEn": "Golden sample flight", "titleAr": "طيران العينة الذهبية", "modelId": _model_id(api),
        "trialDate": "2026-10-20", "statusCode": "PLANNED", "notesAr": "ملاحظة"})
    assert res.status_code == 201, res.get_json()
    return res.get_json()


# ---------------------------------------------------------------- golden-sample trials

def test_golden_sample_trial_with_its_three_scans(app, admin, viewer):
    testing = Api(app, "mock.test")
    demo = viewer.json("/api/v1/golden-samples")["kpis"]
    assert demo["total"] == 4 and demo["passed"] == 1 and demo["planned"] == 1 and demo["complete"] == 0
    assert admin.json("/api/v1/golden-samples/next-code")["code"] == "GS-005"
    trial = _new_trial(testing)
    assert trial["attachments"] == {"GOLDEN_TRIAL": None, "DIRECTIVE_LETTER": None, "OFFICIAL_TRIAL_FORM": None}
    d = viewer.json("/api/v1/golden-samples")
    assert d["kpis"]["total"] == 5 and d["kpis"]["planned"] == 2 and d["kpis"]["missing"] == 5
    for slot in ("GOLDEN_TRIAL", "DIRECTIVE_LETTER", "OFFICIAL_TRIAL_FORM"):
        assert _attach(testing, "GOLDEN_SAMPLE_TRIAL", trial["id"], slot).status_code == 201
    d = viewer.json("/api/v1/golden-samples")
    assert d["kpis"]["complete"] == 1 and d["kpis"]["missing"] == 4
    item = next(e for e in d["items"] if e["id"] == trial["id"])
    assert item["attachments"]["DIRECTIVE_LETTER"]["fileName"] == "scan.pdf"
    # The scan opens through the document's own (permission-checked) address.
    res = viewer.get(f"/api/v1/documents/{item['attachments']['DIRECTIVE_LETTER']['id']}/file")
    assert res.status_code == 200 and res.data == PDF


def test_golden_sample_trials_are_edited_by_the_testing_team_only(app, admin, viewer):
    body = {"code": "GS-009", "titleEn": "Trial", "titleAr": "تجربة", "modelId": _model_id(admin), "trialDate": "2026-10-20",
            "statusCode": "PLANNED"}
    assert viewer.post("/api/v1/golden-samples", json=body).status_code == 403
    trial = _new_trial(Api(app, "mock.test"))
    res = admin.patch(f"/api/v1/golden-samples/{trial['id']}", json={"statusCode": "PASSED", "version": trial["version"],
                                                                       "reason": "Signed off"})
    assert res.status_code == 200 and res.get_json()["status"] == "PASSED"
    assert admin.json(f"/api/v1/history/GOLDEN_SAMPLE_TRIAL/{trial['id']}")["items"][0]["reason"] == "Signed off"
    assert admin.patch(f"/api/v1/golden-samples/{trial['id']}", json={"statusCode": "NOPE"}).status_code == 400


# ---------------------------------------------------------------- scans in slots

def test_a_slot_keeps_one_document_and_each_new_scan_is_a_version(admin):
    test = admin.json("/api/v1/tests")["items"][0]
    first = _attach(admin, "TEST_EVENT", test["id"], "CAPABILITY_DEED")
    assert first.status_code == 201, first.get_json()
    second = _attach(admin, "TEST_EVENT", test["id"], "CAPABILITY_DEED", b"%PDF-1.4 rescanned", "deed-2.pdf")
    assert second.get_json()["id"] == first.get_json()["id"] and second.get_json()["currentVersion"] == 2
    assert first.get_json()["docType"] == "CAPABILITY_DEED" and first.get_json()["titleAr"].startswith("سند القدرة")
    item = next(e for e in admin.json("/api/v1/tests")["items"] if e["id"] == test["id"])
    assert item["attachments"]["CAPABILITY_DEED"]["version"] == 2 and item["attachments"]["LIVE_DEMO_REPORT"] is None
    assert _attach(admin, "TEST_EVENT", test["id"], "LIVE_DEMO_REPORT").status_code == 201


def test_a_refused_scan_leaves_nothing_behind(admin, viewer):
    test = admin.json("/api/v1/tests")["items"][0]
    before = len(admin.json("/api/v1/documents")["items"])
    assert _attach(admin, "TEST_EVENT", test["id"], "CAPABILITY_DEED", b"MZ\x90 not a scan", "deed.pdf").status_code == 400
    assert _attach(admin, "TEST_EVENT", test["id"], "INVESTIGATION").status_code == 400      # not a test's slot
    assert _attach(admin, "PROJECT", 1, "REPORT").status_code == 400                           # no slots on projects
    assert _attach(viewer, "TEST_EVENT", test["id"], "CAPABILITY_DEED").status_code == 403    # no documents permission
    assert len(admin.json("/api/v1/documents")["items"]) == before


def test_capability_maintenance_reason_and_investigation_board(app, admin):
    maint = Api(app, "mock.maint")
    items = admin.json("/api/v1/maintenance")["items"]
    assert next(m for m in items if m["code"] == "MNT-004")["entryReasonAr"].startswith("فقدان وصلة التحكم")
    order = next(m for m in items if m["code"] == "MNT-006")
    assert order["entryReasonAr"] is None and order["attachments"] == {"INVESTIGATION": None}
    res = maint.patch(f"/api/v1/maintenance/{order['id']}", json={
        "entryReasonAr": "عطل في نظام الملاحة أثناء المهمة", "entryReasonEn": "Navigation fault during a mission",
        "version": order["version"]})
    assert res.status_code == 200 and res.get_json()["entryReasonAr"] == "عطل في نظام الملاحة أثناء المهمة"
    assert _attach(maint, "MAINTENANCE_ORDER", order["id"], "INVESTIGATION").status_code == 201
    again = next(m for m in admin.json("/api/v1/maintenance")["items"] if m["id"] == order["id"])
    assert again["attachments"]["INVESTIGATION"]["fileName"] == "scan.pdf"


# ---------------------------------------------------------------- the culture library

def test_culture_library_holds_references_guides_and_acquisition_plans(admin, viewer):
    code = admin.json("/api/v1/documents/next-code")["code"]
    res = admin.post("/api/v1/documents", json={"code": code, "titleEn": "Doctrine", "titleAr": "العقيدة", "docType": "REFERENCE",
                                                "entityType": "LIBRARY", "entityId": "1"})
    assert res.status_code == 201, res.get_json()
    doc = res.get_json()
    assert doc["linked"]["link"] == "/culture/references" and doc["department"] is None
    from tests.integration.test_documents_alerts_settings import _upload
    assert _upload(admin, doc["id"], PDF).status_code == 201
    items = viewer.json("/api/v1/documents?entityType=LIBRARY&type=REFERENCE")["items"]
    assert [d["code"] for d in items] == [code] and items[0]["latest"]["fileName"] == "file.pdf"
    assert viewer.json("/api/v1/documents?entityType=LIBRARY&type=USER_GUIDE")["items"] == []
    # Library kinds only in the library, and the library only for them.
    wrong = {"code": "DOC-900", "titleEn": "x x", "titleAr": "س س", "entityType": "LIBRARY", "entityId": "1", "docType": "REPORT"}
    assert admin.post("/api/v1/documents", json=wrong).status_code == 400
    assert admin.post("/api/v1/documents", json={**wrong, "entityType": "PROJECT", "docType": "ACQUISITION_PLAN"}).status_code == 400
    assert admin.post("/api/v1/documents", json={**wrong, "docType": "USER_GUIDE", "entityId": "2"}).status_code == 400
    assert viewer.post("/api/v1/documents", json={**wrong, "docType": "USER_GUIDE"}).status_code == 403
