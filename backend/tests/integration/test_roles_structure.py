"""The organisation's structure as the standard roles (owner, 25 Nov 2026): the commander and the system administrator,
under them the head of the Capability Development Section, under that head the heads of the Security Systems and
Unmanned Systems sections, then the project manager, then the user. The five heads of the structure have every
permission; the project manager and the user add and view only (no records.change). Role levels in Settings > Roles,
and the schema script that brought both (db/sqlite/V008)."""
from __future__ import annotations

import io
import shutil
import sqlite3

from sqlalchemy import create_engine

from app.core.config import SQLITE_MIGRATIONS_DIR
from app.core.database import migrate_sqlite
from tests.conftest import Api

STRUCTURE = [("COMMANDER", 1, "القائد"), ("SYS_ADMIN", 1, "مدير النظام"), ("HEAD_CAP_DEV", 2, "رئيس شعبة تطوير القدرات"),
             ("HEAD_SECURITY", 3, "رئيس شعبة الأنظمة الأمنية"), ("HEAD_UNMANNED", 3, "رئيس شعبة الأنظمة المسيّرة"),
             ("PROJECT_MGR", 4, "مدير المشروع"), ("USER", 5, "المستخدم")]
PDF = b"%PDF-1.4 scanned page"


def _attach(api, entity_type, entity_id, doc_type):
    form = {"entityType": entity_type, "entityId": str(entity_id), "docType": doc_type, "file": (io.BytesIO(PDF), "scan.pdf")}
    return api.client.post("/api/v1/attachments", data=form, content_type="multipart/form-data",
                           headers={"X-CSRF-Token": api.csrf})


def _add_only(res) -> bool:
    return res.status_code == 403 and res.get_json()["code"] == "ADD_ONLY"


def test_the_standard_roles_are_the_organisation_structure(admin):
    d = admin.json("/api/v1/admin/roles")
    placed = [(r["code"], r["tier"], r["nameAr"]) for r in d["items"] if r["tier"]]
    assert placed == STRUCTURE
    roles = {r["code"]: r for r in d["items"]}
    every = sorted(d["permissions"])
    assert "records.change" in every
    for code in ("COMMANDER", "SYS_ADMIN", "HEAD_CAP_DEV", "HEAD_SECURITY", "HEAD_UNMANNED"):
        assert roles[code]["permissions"] == every and roles[code]["scope"] == "ALL"
    for code in ("PROJECT_MGR", "USER"):
        perms = set(roles[code]["permissions"])
        assert {"view", "reports.view"} <= perms and {p for p in every if p.startswith("edit.")} <= perms
        assert not perms & {"records.change", "admin", "export", "reports.exec", "reports.build", "reports.schedule",
                            "tracking.view"}
    # One demo account per role of the structure.
    people = {u["username"]: u["role"] for u in admin.json("/api/v1/users?size=100")["items"]}
    assert {people[n] for n in ("mock.commander", "mock.admin", "mock.capdev", "mock.security", "mock.unmanned",
                                "mock.pm", "mock.user")} == {code for code, _, _ in STRUCTURE}


def test_the_heads_of_the_structure_may_do_everything(app, commander, capdev):
    assert commander.get("/api/v1/tracking/actions").status_code == 200    # user tracking
    assert capdev.get("/api/v1/admin/roles").status_code == 200            # settings
    security = Api(app, "mock.security")
    asset = security.json("/api/v1/assets?size=1")["items"][0]
    archived = security.post(f"/api/v1/assets/{asset['id']}/archive", json={"archived": True, "version": asset["version"]})
    assert archived.status_code == 200, archived.get_json()
    restored = Api(app, "mock.unmanned").post(f"/api/v1/assets/{asset['id']}/archive",
                                              json={"archived": False, "version": archived.get_json()["version"]})
    assert restored.status_code == 200, restored.get_json()


def test_the_project_manager_and_the_user_add_and_view_only(app, admin, pm, staff):
    session = staff.json("/api/v1/session")["user"]
    assert "records.change" not in session["permissions"] and "edit.assets" in session["permissions"]
    assert staff.get("/api/v1/assets").status_code == 200 and pm.get("/api/v1/projects").status_code == 200
    assert staff.get("/api/v1/admin/roles").status_code == 403 and pm.get("/api/v1/tracking/actions").status_code == 403
    # The project manager adds a risk to a project, and cannot change it afterwards; a head can.
    pid = admin.json("/api/v1/projects?size=1")["items"][0]["id"]
    added = pm.post("/api/v1/risks", json={"code": "RSK-098", "projectId": pid, "titleEn": "Added risk",
                                          "titleAr": "خطر مضاف", "category": "TECHNICAL", "probability": 2, "impact": 2,
                                          "statusCode": "OPEN"})
    assert added.status_code == 201, added.get_json()
    risk = added.get_json()
    assert _add_only(pm.patch(f"/api/v1/risks/{risk['id']}", json={"probability": 3, "version": risk["version"]}))
    assert admin.patch(f"/api/v1/risks/{risk['id']}", json={"probability": 3, "version": risk["version"]}).status_code == 200
    # The user adds a golden-sample trial; changing it, or archiving a record, is refused.
    model_id = admin.json("/api/v1/models?size=1")["items"][0]["id"]
    trial = staff.post("/api/v1/golden-samples", json={"code": "GS-201", "titleEn": "Added trial", "titleAr": "تجربة مضافة",
                                                       "modelId": model_id, "trialDate": "2026-10-20",
                                                       "statusCode": "PLANNED"})
    assert trial.status_code == 201, trial.get_json()
    assert _add_only(staff.patch(f"/api/v1/golden-samples/{trial.get_json()['id']}",
                                 json={"statusCode": "PASSED", "version": trial.get_json()["version"]}))
    asset = staff.json("/api/v1/assets?size=1")["items"][0]
    assert _add_only(staff.post(f"/api/v1/assets/{asset['id']}/archive", json={"archived": True, "version": asset["version"]}))
    assert _add_only(pm.post(f"/api/v1/projects/{pid}/archive", json={"archived": True}))


def test_a_first_scan_is_adding_and_replacing_it_is_a_change(admin, staff):
    model_id = admin.json("/api/v1/models?size=1")["items"][0]["id"]
    trial = staff.post("/api/v1/golden-samples", json={"code": "GS-202", "titleEn": "Trial with scans", "titleAr": "تجربة بمرفقات",
                                                       "modelId": model_id, "trialDate": "2026-10-21",
                                                       "statusCode": "PLANNED"}).get_json()
    assert _attach(staff, "GOLDEN_SAMPLE_TRIAL", trial["id"], "GOLDEN_TRIAL").status_code == 201
    assert _add_only(_attach(staff, "GOLDEN_SAMPLE_TRIAL", trial["id"], "GOLDEN_TRIAL"))   # a second file replaces it
    assert _attach(admin, "GOLDEN_SAMPLE_TRIAL", trial["id"], "GOLDEN_TRIAL").status_code == 201


def test_a_role_level_is_set_in_settings_and_audited(admin, staff):
    roles = {r["code"]: r for r in admin.json("/api/v1/admin/roles")["items"]}
    user_role = roles["USER"]
    res = admin.patch(f"/api/v1/admin/roles/{user_role['id']}", json={"tier": 6, "version": user_role["version"]})
    assert res.status_code == 200 and res.get_json()["tier"] == 6
    assert {r["code"]: r["tier"] for r in admin.json("/api/v1/lookups")["roles"]}["USER"] == 6
    history = admin.json(f"/api/v1/audit?entityType=APP_ROLE&entityId={user_role['id']}")["items"]
    assert {"field": "tier", "from": 5, "to": 6} in history[0]["changes"]
    for wrong in (25, -1, "3", True):
        bad = admin.patch(f"/api/v1/admin/roles/{user_role['id']}", json={"tier": wrong})
        assert bad.status_code == 400 and bad.get_json()["fieldErrors"][0]["field"] == "tier"
    made = admin.post("/api/v1/admin/roles", json={"code": "SECTION_CLERK", "nameEn": "Section clerk", "nameAr": "كاتب الشعبة",
                                                   "tier": 5, "permissions": ["view"]})
    assert made.status_code == 201 and made.get_json()["tier"] == 5
    assert staff.patch(f"/api/v1/admin/roles/{user_role['id']}", json={"tier": 1}).status_code == 403


def test_the_schema_script_lets_the_roles_that_edited_keep_changing(tmp_path):
    """db/sqlite/V008 on a database of before: an editing role gets records.change, a reading one does not, and both
    are placed nowhere (level 0)."""
    before = tmp_path / "before"
    before.mkdir()
    upto = tmp_path / "upto8"
    upto.mkdir()
    for script in SQLITE_MIGRATIONS_DIR.glob("V*.sql"):
        if int(script.name[1:4]) < 8:
            shutil.copy(script, before / script.name)
        if int(script.name[1:4]) <= 8:
            shutil.copy(script, upto / script.name)
    path = tmp_path / "old.db"
    engine = create_engine(f"sqlite:///{path.as_posix()}")
    migrate_sqlite(engine, before)
    stamp = "2026-11-01 08:00:00.000000"
    with sqlite3.connect(path) as conn:
        for code in ("EDITOR", "READER"):
            conn.execute("INSERT INTO APP_ROLE (code, name_en, name_ar, scope, created_at, updated_at) "
                         "VALUES (?, ?, ?, 'ALL', ?, ?)", (code, code.title(), code.title(), stamp, stamp))
        ids = dict(conn.execute("SELECT code, id FROM APP_ROLE"))
        conn.executemany("INSERT INTO ROLE_PERMISSION (role_id, permission, created_at) VALUES (?, ?, ?)",
                         [(ids["EDITOR"], "view", stamp), (ids["EDITOR"], "edit.assets", stamp),
                          (ids["EDITOR"], "edit.projects", stamp), (ids["READER"], "view", stamp)])
    assert migrate_sqlite(engine, upto) == ["V008__role_levels_and_change.sql"]
    engine.dispose()
    with sqlite3.connect(path) as conn:
        perms = {(code, p) for code, p in conn.execute(
            "SELECT r.code, p.permission FROM ROLE_PERMISSION p JOIN APP_ROLE r ON r.id = p.role_id")}
        tiers = dict(conn.execute("SELECT code, tier FROM APP_ROLE"))
        try:
            conn.execute("INSERT INTO ROLE_PERMISSION (role_id, permission, created_at) VALUES (?, 'nonsense', ?)",
                         (ids["READER"], stamp))
            refused = False
        except sqlite3.IntegrityError:
            refused = True
    assert perms == {("EDITOR", "view"), ("EDITOR", "edit.assets"), ("EDITOR", "edit.projects"),
                     ("EDITOR", "records.change"), ("READER", "view")}
    assert tiers == {"EDITOR": 0, "READER": 0} and refused
