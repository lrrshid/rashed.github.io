"""Documents (versioned, type-checked uploads, scope), alerts (rules, roles, acknowledgement), settings administration."""
from __future__ import annotations

import io


def _upload(api, doc_id, data, name="file.pdf", note=None):
    form = {"file": (io.BytesIO(data), name)}
    if note:
        form["note"] = note
    return api.client.post(f"/api/v1/documents/{doc_id}/versions", data=form, content_type="multipart/form-data",
                           headers={"X-CSRF-Token": api.csrf})


def test_document_versions_are_kept_and_downloadable(admin):
    docs = admin.json("/api/v1/documents")["items"]
    assert len(docs) == 8
    doc = next(d for d in docs if d["code"] == "DOC-001")
    assert doc["currentVersion"] == 2
    res = _upload(admin, doc["id"], b"%PDF-1.4 revision three", note="Rev 3")
    assert res.status_code == 201, res.get_json()
    detail = res.get_json()
    assert detail["currentVersion"] == 3 and [v["versionNo"] for v in detail["versions"]] == [3, 2, 1]
    first = admin.get(f"/api/v1/documents/{doc['id']}/file?version=1")
    assert first.status_code == 200 and first.mimetype == "application/pdf" and first.data.startswith(b"%PDF")


def test_upload_type_is_decided_from_the_bytes(admin):
    doc_id = admin.json("/api/v1/documents")["items"][0]["id"]
    assert _upload(admin, doc_id, b"MZ\x90\x00 not a pdf", name="report.pdf").status_code == 400
    assert _upload(admin, doc_id, b"plain text\nline", name="notes.txt").status_code == 201


def test_upload_needs_the_documents_permission(viewer, admin):
    doc_id = admin.json("/api/v1/documents")["items"][0]["id"]
    assert _upload(viewer, doc_id, b"%PDF-1.4 x").status_code == 403


def test_documents_follow_the_department_scope(head, admin):
    project_docs = [d for d in admin.json("/api/v1/documents")["items"] if d["department"]]
    other = next(d for d in project_docs if d["department"]["code"] != "G2")
    assert head.get(f"/api/v1/documents/{other['id']}").status_code == 404
    assert all(d["department"] is None or d["department"]["code"] == "G2" for d in head.json("/api/v1/documents")["items"])


def test_alerts_are_role_based_and_acknowledged_per_user(admin, commander, staff):
    types_admin = {a["type"] for a in admin.json("/api/v1/alerts")["items"]}
    types_user = {a["type"] for a in staff.json("/api/v1/alerts")["items"]}  # the field ones, not the budget
    assert "SPARE_PARTS_SHORTAGE" in types_user and "BUDGET_OVERRUN" not in types_user
    assert "BUDGET_OVERRUN" in types_admin
    before = commander.json("/api/v1/alerts/count")["open"]
    key = commander.json("/api/v1/alerts")["items"][0]["key"]
    assert commander.post("/api/v1/alerts/acknowledge", json={"keys": [key]}).status_code == 200
    assert commander.json("/api/v1/alerts/count")["open"] == before - 1
    assert admin.json("/api/v1/alerts?open=true")["open"] == admin.json("/api/v1/alerts/count")["open"]


def test_alert_rule_change_hides_a_type(admin, commander, staff):
    assert any(a["type"] == "PROJECT_DELAYED" for a in commander.json("/api/v1/alerts")["items"])
    rules = {r["type"]: r for r in admin.json("/api/v1/alert-rules")["items"]}
    rule = rules["PROJECT_DELAYED"]
    res = admin.put("/api/v1/alert-rules/PROJECT_DELAYED", json={"roles": ["SYS_ADMIN"], "enabled": True,
                                                                 "version": rule["version"]})
    assert res.status_code == 200, res.get_json()
    assert not any(a["type"] == "PROJECT_DELAYED" for a in commander.json("/api/v1/alerts")["items"])
    assert staff.put("/api/v1/alert-rules/PROJECT_DELAYED", json={"roles": [], "enabled": False}).status_code == 403


def test_settings_lists_are_admin_only_and_audited(admin, capability):
    assert capability.get("/api/v1/admin/lists/sites").status_code == 403
    res = admin.post("/api/v1/admin/lists/sites", json={"code": "NSB", "nameEn": "New Sea Base", "nameAr": "قاعدة بحرية جديدة"})
    assert res.status_code == 201, res.get_json()
    site = res.get_json()
    upd = admin.patch(f"/api/v1/admin/lists/sites/{site['id']}", json={"nameEn": "North Sea Base", "version": site["version"]})
    assert upd.status_code == 200 and upd.get_json()["nameEn"] == "North Sea Base"
    events = admin.json("/api/v1/audit?entityType=SITE")["items"]
    assert any(e["action"] == "UPDATE" for e in events)
    assert any(s["code"] == "NSB" for s in admin.json("/api/v1/lookups")["sites"])


def test_status_codes_are_fixed_once_created(admin):
    status = next(s for s in admin.json("/api/v1/admin/lists/statuses")["items"] if s["code"] == "READY")
    res = admin.patch(f"/api/v1/admin/lists/statuses/{status['id']}", json={"code": "READY_NOW", "version": status["version"]})
    assert res.status_code == 409


def test_workflow_stages_can_be_reordered(admin):
    types = admin.json("/api/v1/admin/lists/projectTypes")["items"]
    trials = next(ty for ty in types if ty["code"] == "TRIALS")
    stages = [s for s in admin.json("/api/v1/admin/lists/stages")["items"] if s["projectTypeId"] == trials["id"]]
    ids = [s["id"] for s in sorted(stages, key=lambda s: s["sortOrder"])]
    res = admin.put(f"/api/v1/admin/project-types/{trials['id']}/stage-order", json={"stageIds": list(reversed(ids))})
    assert res.status_code == 200
    assert [s["id"] for s in sorted(res.get_json()["items"], key=lambda s: s["sortOrder"])] == list(reversed(ids))


def test_role_permissions_are_editable_and_take_effect(admin, app):
    from tests.conftest import Api
    roles = {r["code"]: r for r in admin.json("/api/v1/admin/roles")["items"]}
    viewer_role = roles["VIEWER"]
    res = admin.patch(f"/api/v1/admin/roles/{viewer_role['id']}", json={"permissions": ["view", "reports.view", "export"],
                                                                        "version": viewer_role["version"]})
    assert res.status_code == 200
    viewer = Api(app, "mock.viewer")
    assert "export" in viewer.user["permissions"]
    assert viewer.get("/api/v1/assets.csv").status_code == 200
    sys_role = roles["SYS_ADMIN"]
    assert admin.patch(f"/api/v1/admin/roles/{sys_role['id']}", json={"permissions": ["view"]}).status_code == 409


def test_appearance_theme_is_public_and_admin_only_to_change(admin, capability, anon):
    theme = anon.json("/api/v1/appearance")["theme"]
    assert theme == {"sidebar": "#142029", "primary": "#142029", "accent": "#b9995a", "background": "#f3f1ec"}
    green = {"sidebar": "#1f2b1d", "primary": "#2c3d29", "accent": "#b5a46a", "background": "#f1f0ea"}
    assert capability.put("/api/v1/settings/ui.theme", json={"value": green, "version": 0}).status_code == 403
    assert admin.put("/api/v1/settings/ui.theme", json={"value": {**green, "accent": "gold"}, "version": 0}).status_code == 400
    res = admin.put("/api/v1/settings/ui.theme", json={"value": green, "version": 0, "reason": "Green theme"})
    assert res.status_code == 200, res.get_json()
    assert anon.json("/api/v1/appearance")["theme"] == green
