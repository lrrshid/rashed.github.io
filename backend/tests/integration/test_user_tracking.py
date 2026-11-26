"""User tracking «تتبع المستخدمين» (owner, 25 Nov 2026): every action of every person, carried out or refused, with the
record, the reason it failed, the date and time and the device; for the roles given tracking.view (the commander and
the heads of the structure), never in a role preview. Passwords and other request values are never kept; the log is
append-only."""
from __future__ import annotations

import shutil
import sqlite3

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import DBAPIError

from app.core.config import SQLITE_MIGRATIONS_DIR
from app.core.database import migrate_sqlite
from app.extensions import db
from app.models import ActionLog
from tests.conftest import Api

API = "/api/v1/tracking"


def _mine(commander, person: Api, **filters) -> list[dict]:
    """The actions of one person, oldest first."""
    params = "&".join(f"{k}={v}" for k, v in {"user": person.user["id"], "size": 100, **filters}.items())
    return list(reversed(commander.json(f"{API}/actions?{params}")["items"]))


def _new_trial(api: Api, code: str) -> dict:
    model_id = api.json("/api/v1/models?size=1")["items"][0]["id"]
    res = api.post("/api/v1/golden-samples", json={"code": code, "titleEn": "Tracked trial", "titleAr": "تجربة متتبعة",
                                                   "modelId": model_id, "trialDate": "2026-10-20", "statusCode": "PLANNED"})
    assert res.status_code == 201, res.get_json()
    return res.get_json()


def test_every_action_is_kept_with_its_outcome(commander, staff):
    project = staff.json("/api/v1/projects?size=1")["items"][0]
    staff.json(f"/api/v1/projects/{project['id']}")                                         # opened a project
    trial = _new_trial(staff, "GS-301")                                                       # added: carried out
    assert staff.patch(f"/api/v1/golden-samples/{trial['id']}",                               # changed: refused
                       json={"statusCode": "PASSED", "version": trial["version"]}).status_code == 403
    assert staff.get("/api/v1/assets.csv").status_code == 403                                # exported: refused
    rows = _mine(commander, staff)
    assert [(r["action"], r["outcome"], r["errorCode"]) for r in rows] == [
        ("SIGN_IN", "DONE", None), ("VIEW", "DONE", None), ("CREATE", "DONE", None),
        ("UPDATE", "FAILED", "ADD_ONLY"), ("EXPORT", "FAILED", "FORBIDDEN")]
    _, view, created, refused, export = rows
    assert view["record"]["code"] == project["code"] and view["link"] == f"/projects/{project['id']}"
    assert created["entityType"] == "GOLDEN_SAMPLE_TRIAL" and created["record"] == {
        "code": "GS-301", "nameEn": "Tracked trial", "nameAr": "تجربة متتبعة"} and created["changesCount"] == 1
    assert refused["record"]["code"] == "GS-301" and refused["status"] == 403 and refused["method"] == "PATCH"
    assert export["entityType"] == "ASSET" and export["errorMessage"]
    for row in rows:
        assert row["user"]["username"] == "mock.user" and row["user"]["role"] == "USER"
        assert row["occurredAt"].endswith("Z") and row["ip"] == "127.0.0.1" and row["requestId"]
    summary = commander.json(f"{API}/actions?user={staff.user['id']}")["summary"]
    assert summary == {"total": 5, "done": 3, "failed": 2, "failedSignIns": 0, "people": 1}


def test_sign_ins_are_kept_failed_ones_too_and_never_a_password(app, commander):
    stranger = Api(app, None)
    assert stranger.client.post("/api/v1/session", json={"username": "mock.pm", "password": "Wrong-Secret-9"}).status_code == 401
    assert stranger.client.post("/api/v1/session", json={"username": "nobody.here",
                                                         "password": "Typed-Secret-77"}).status_code == 401
    person = Api(app, "mock.pm")
    person.delete("/api/v1/session")
    sessions = commander.json(f"{API}/actions?kind=SESSION&size=100")["items"]
    failed = [r for r in sessions if r["outcome"] == "FAILED"]
    assert {(r["user"]["username"], r["errorCode"]) for r in failed} == {("mock.pm", "LOGIN_FAILED"), ("nob***", "LOGIN_FAILED")}
    assert next(r for r in failed if r["user"]["username"] == "mock.pm")["user"]["id"] == person.user["id"]
    pm_rows = [(r["action"], r["outcome"]) for r in reversed(sessions) if r["user"]["username"] == "mock.pm"]
    assert pm_rows == [("SIGN_IN", "FAILED"), ("SIGN_IN", "DONE"), ("SIGN_OUT", "DONE")]
    assert commander.json(f"{API}/actions?kind=SESSION")["summary"]["failedSignIns"] == 2
    with app.app_context():
        kept = " ".join(str(v) for row in db.session().scalars(select(ActionLog))
                        for v in vars(row).values())
    assert "Wrong-Secret-9" not in kept and "Typed-Secret-77" not in kept and "Mock-Pass-123" not in kept
    assert "nobody.here" not in kept  # a name that is no account (perhaps a password in the wrong box): first letters only
    assert all(r["record"]["code"] is None for r in sessions)


def test_a_change_carried_out_shows_what_changed(admin, commander):
    risk = admin.json("/api/v1/risks?size=1")["items"][0]
    new = 1 if risk["probability"] != 1 else 2
    res = admin.patch(f"/api/v1/risks/{risk['id']}", json={"probability": new, "version": risk["version"],
                                                          "reason": "Tracking test"})
    assert res.status_code == 200, res.get_json()
    row = commander.json(f"{API}/actions?q={risk['code']}&kind=CHANGE")["items"][0]
    assert row["action"] == "UPDATE" and row["outcome"] == "DONE" and row["user"]["username"] == "mock.admin"
    detail = commander.json(f"{API}/actions/{row['id']}")
    assert {"field": "probability", "from": risk["probability"], "to": new} in detail["changes"]
    assert detail["reason"] == "Tracking test" and detail["record"]["code"] == risk["code"]


def test_uploads_and_downloads_name_the_file(admin, commander):
    trial = _new_trial(admin, "GS-302")
    import io
    form = {"entityType": "GOLDEN_SAMPLE_TRIAL", "entityId": trial["id"], "docType": "GOLDEN_TRIAL",
            "file": (io.BytesIO(b"%PDF-1.4 scan"), "signed-trial.pdf")}
    res = admin.client.post("/api/v1/attachments", data=form, content_type="multipart/form-data",
                            headers={"X-CSRF-Token": admin.csrf})
    assert res.status_code == 201, res.get_json()
    document = res.get_json()
    assert admin.get(f"/api/v1/documents/{document['id']}/file").status_code == 200
    rows = _mine(commander, admin, kind="FILES")
    upload, download = rows[-2], rows[-1]
    assert upload["action"] == "UPLOAD" and upload["entityType"] == "GOLDEN_SAMPLE_TRIAL"
    assert upload["record"]["code"] == "GS-302" and upload["detail"] == "GOLDEN_TRIAL · signed-trial.pdf"
    assert download["action"] == "DOWNLOAD" and download["entityType"] == "DOCUMENT" and download["detail"]


def test_only_the_roles_given_tracking_see_it(app, admin, commander, capdev, pm, staff):
    for person in (admin, commander, capdev):
        assert person.get(f"{API}/actions").status_code == 200
    for person in (pm, staff):
        assert person.get(f"{API}/actions").status_code == 403 and person.get(f"{API}/users").status_code == 403
    assert admin.get(f"{API}/actions", headers={"X-View-As": "COMMANDER"}).status_code == 403  # never in a preview
    assert commander.get(f"{API}/actions/999999").status_code == 404
    assert commander.get(f"{API}/actions?kind=NOPE").status_code == 400
    assert commander.get(f"{API}/actions?from=2020-01-01&to=2020-01-31").get_json()["totalItems"] == 0
    # The users summary: everyone, with sign-ins, actions and the ones refused.
    staff.patch(f"/api/v1/projects/{staff.json('/api/v1/projects?size=1')['items'][0]['id']}", json={"nameEn": "x"})
    people = {u["username"]: u for u in commander.json(f"{API}/users")["items"]}
    assert people["mock.user"]["signIns"] == 1 and people["mock.user"]["failed"] == 1
    assert people["mock.user"]["online"] is True and people["mock.user"]["lastActivity"]
    assert people["mock.user"]["role"]["nameAr"] == "المستخدم"


def test_the_log_is_append_only(app, commander):
    with app.app_context():
        for statement in ("UPDATE ACTION_LOG SET username = 'someone'", "DELETE FROM ACTION_LOG"):
            with pytest.raises(DBAPIError):
                db.session().execute(text(statement))
            db.session().rollback()
        assert db.session().scalar(select(ActionLog.id).limit(1)) is not None


def test_the_schema_script_gives_tracking_to_the_roles_that_administer(tmp_path):
    """db/sqlite/V009 on a database of before: a role holding admin is given tracking.view, another is not."""
    before = tmp_path / "before"
    before.mkdir()
    for script in SQLITE_MIGRATIONS_DIR.glob("V*.sql"):
        if int(script.name[1:4]) < 9:
            shutil.copy(script, before / script.name)
    path = tmp_path / "old.db"
    engine = create_engine(f"sqlite:///{path.as_posix()}")
    migrate_sqlite(engine, before)
    stamp = "2026-11-01 08:00:00.000000"
    with sqlite3.connect(path) as conn:
        for code in ("CHIEF", "CLERK"):
            conn.execute("INSERT INTO APP_ROLE (code, name_en, name_ar, scope, created_at, updated_at) "
                         "VALUES (?, ?, ?, 'ALL', ?, ?)", (code, code.title(), code.title(), stamp, stamp))
        ids = dict(conn.execute("SELECT code, id FROM APP_ROLE"))
        conn.executemany("INSERT INTO ROLE_PERMISSION (role_id, permission, created_at) VALUES (?, ?, ?)",
                         [(ids["CHIEF"], "view", stamp), (ids["CHIEF"], "admin", stamp), (ids["CLERK"], "view", stamp)])
    assert migrate_sqlite(engine, SQLITE_MIGRATIONS_DIR) == ["V009__action_log.sql"]
    engine.dispose()
    with sqlite3.connect(path) as conn:
        perms = {(code, p) for code, p in conn.execute(
            "SELECT r.code, p.permission FROM ROLE_PERMISSION p JOIN APP_ROLE r ON r.id = p.role_id")}
        assert conn.execute("SELECT COUNT(*) FROM ACTION_LOG").fetchone()[0] == 0
    assert perms == {("CHIEF", "view"), ("CHIEF", "admin"), ("CHIEF", "tracking.view"), ("CLERK", "view")}
