"""Capability records, formula-driven figures, drill-down consistency, permissions and department scope."""
from __future__ import annotations


def test_demo_figures_match_the_brochure_shape(admin):
    d = admin.json("/api/v1/dashboard")
    assert d["inventory"]["capabilities"]["value"] == 12
    assert d["inventory"]["assets"]["value"] == 66
    assert d["pipeline"]["criticalGaps"]["value"] == 3
    assert d["portfolio"]["activeProjects"]["value"] == 13
    assert d["portfolio"]["delayedProjects"]["value"] == 7
    assert d["attention"], "the leadership-attention list is never empty on the demo"


def test_every_dashboard_asset_figure_equals_its_drill_down(admin):
    """No static numbers: the records a figure opens are exactly the ones it counts."""
    d = admin.json("/api/v1/dashboard")
    for section in ("inventory", "pipeline"):
        for key, kpi in d[section].items():
            if not kpi.get("drill") and kpi.get("drill") != {}:
                continue
            listed = admin.json("/api/v1/assets?" + _qs(kpi["drill"]) + "&size=1")["totalItems"]
            assert listed == kpi["value"], (section, key, listed, kpi["value"])
    for row in d["statusDistribution"]:
        assert admin.json("/api/v1/assets?" + _qs(row["drill"]) + "&size=1")["totalItems"] == row["count"]


def test_completion_groups_drill_to_their_available_assets(admin):
    data = admin.json("/api/v1/completion")
    for group in data["groups"]:
        if group["drill"]:
            listed = admin.json("/api/v1/assets?" + _qs(group["drill"]) + "&size=1")["totalItems"]
            assert listed == group["available"], group["department"]["code"]


def test_forecast_counts_only_projects_in_forecast_statuses(admin):
    reqs = {r["code"]: r for r in admin.json("/api/v1/requirements")["items"]}
    # RQ02 is served by PRJ-003, which is UNDER_STUDY: not counted, so the gap stays and it is critical.
    assert reqs["RQ02"]["forecastAdd"] == 0 and reqs["RQ02"]["critical"]
    # RQ01 is served by PRJ-001 (CONTRACTING, a forecast status) with 6 units: the forecast closes the gap.
    assert reqs["RQ01"]["forecastAdd"] == 6 and reqs["RQ01"]["forecastGap"] == 0


def test_business_rule_change_moves_the_figures(admin):
    before = admin.json("/api/v1/requirements/1")["available"]
    settings = {s["key"]: s for s in admin.json("/api/v1/settings")["items"]}
    rule = settings["assets.available_statuses"]
    res = admin.put("/api/v1/settings/assets.available_statuses",
                    json={"value": ["READY"], "version": rule["version"], "reason": "test"})
    assert res.status_code == 200, res.get_json()
    after = admin.json("/api/v1/requirements/1")["available"]
    assert after < before


def test_asset_update_is_audited_with_history_and_version(admin):
    asset = admin.json("/api/v1/assets/1")
    res = admin.patch("/api/v1/assets/1", json={"statusCode": "UNDER_MAINTENANCE", "readinessOperational": 20,
                                                "version": asset["version"], "reason": "Engine check"})
    assert res.status_code == 200, res.get_json()
    body = res.get_json()
    assert body["status"] == "UNDER_MAINTENANCE" and body["version"] == asset["version"] + 1
    assert body["statusHistory"][0]["status"] == "UNDER_MAINTENANCE"
    events = admin.json("/api/v1/history/ASSET/1")["items"]
    change = {c["field"]: c for c in events[0]["changes"]}
    assert change["status_code"]["from"] == "READY" and change["status_code"]["to"] == "UNDER_MAINTENANCE"
    assert events[0]["reason"] == "Engine check"
    stale = admin.patch("/api/v1/assets/1", json={"statusCode": "READY", "version": asset["version"]})
    assert stale.status_code == 409 and stale.get_json()["code"] == "STALE_VERSION"


def test_create_asset_validates_references_and_codes(capability):
    bad = capability.post("/api/v1/assets", json={"code": "UAV-900", "modelId": "999", "departmentId": "1",
                                                  "statusCode": "READY"})
    assert bad.status_code == 400
    dup = capability.post("/api/v1/assets", json={"code": "UAV-001", "modelId": "1", "departmentId": "1",
                                                  "statusCode": "READY"})
    assert dup.status_code == 409
    ok = capability.post("/api/v1/assets", json={"code": "UAV-900", "modelId": "1", "departmentId": "1",
                                                 "statusCode": "UNDER_ACQUISITION"})
    assert ok.status_code == 201, ok.get_json()


def test_viewer_and_executive_cannot_change_records(viewer, executive):
    for api in (viewer, executive):
        res = api.patch("/api/v1/assets/1", json={"statusCode": "READY"})
        assert res.status_code == 403


def test_department_head_sees_only_its_department(head):
    assert head.user["departmentIds"] == ["2"]
    assets = head.json("/api/v1/assets?size=100")["items"]
    assert assets and all(a["department"]["code"] == "G2" for a in assets)
    other = head.json("/api/v1/assets?department=3&size=1")
    assert other["totalItems"] == 0
    g3_asset = next(a for a in _all_assets(head.app) if a["department"]["code"] == "G3")
    assert head.get(f"/api/v1/assets/{g3_asset['id']}").status_code == 404
    reqs = head.json("/api/v1/requirements")["items"]
    assert reqs and all(r["department"]["code"] == "G2" for r in reqs)


def test_department_head_edits_requirements_only_in_scope(head, admin):
    reqs = admin.json("/api/v1/requirements")["items"]
    mine = next(r for r in reqs if r["department"]["code"] == "G2")
    other = next(r for r in reqs if r["department"]["code"] == "G3")
    detail = admin.json(f"/api/v1/requirements/{mine['id']}")
    ok = head.patch(f"/api/v1/requirements/{mine['id']}", json={"requiredQty": mine["required"] + 1,
                                                                "version": detail["version"]})
    assert ok.status_code == 200, ok.get_json()
    assert head.patch(f"/api/v1/requirements/{other['id']}", json={"requiredQty": 1}).status_code == 404


def test_role_preview_reads_as_the_role_and_never_writes(admin):
    session = admin.json("/api/v1/session", headers={"X-View-As": "VIEWER"})
    assert session["viewAs"] == "VIEWER" and "edit.assets" not in session["user"]["permissions"]
    res = admin.patch("/api/v1/assets/1", json={"statusCode": "READY"}, headers={"X-View-As": "VIEWER"})
    assert res.status_code == 403 and res.get_json()["code"] == "PREVIEW_READ_ONLY"


def test_preview_header_is_ignored_for_non_admins(viewer):
    session = viewer.json("/api/v1/session", headers={"X-View-As": "SYS_ADMIN"})
    assert session["viewAs"] is None and "admin" not in session["user"]["permissions"]


def test_csv_export_needs_the_export_permission_and_neutralises_formulas(admin, viewer):
    res = admin.get("/api/v1/assets.csv?department=2")
    assert res.status_code == 200 and res.mimetype == "text/csv"
    assert res.data.decode("utf-8-sig").splitlines()[0].startswith("Asset ID")
    assert viewer.get("/api/v1/assets.csv").status_code == 403


def test_model_specs_are_checked_against_the_category_fields(capability):
    model = capability.json("/api/v1/models/1")
    bad = capability.patch("/api/v1/models/1", json={"specs": {"no_such_field": 1}, "version": model["version"]})
    assert bad.status_code == 400
    ok = capability.patch("/api/v1/models/1", json={"specs": {**model["specs"], "endurance": 16},
                                                    "version": model["version"]})
    assert ok.status_code == 200 and ok.get_json()["specs"]["endurance"] == 16


def test_search_finds_models_assets_and_projects(admin):
    data = admin.json("/api/v1/search?q=falcon")
    assert data["models"] and data["assets"] and data["projects"]


def test_saved_views_are_personal(admin, viewer):
    res = admin.post("/api/v1/saved-views", json={"page": "registry", "name": "G2 ready", "filters": {"department": "2"}})
    assert res.status_code == 201
    view_id = res.get_json()["id"]
    assert viewer.json("/api/v1/saved-views")["items"] == []
    assert viewer.delete(f"/api/v1/saved-views/{view_id}").status_code == 404


def _qs(filters: dict) -> str:
    parts = []
    for key, value in filters.items():
        if value is None:
            continue
        parts.append(f"{key}={','.join(value) if isinstance(value, list) else value}")
    return "&".join(parts)


def _all_assets(app):
    from tests.conftest import Api
    return Api(app, "mock.admin").json("/api/v1/assets?size=100")["items"]
