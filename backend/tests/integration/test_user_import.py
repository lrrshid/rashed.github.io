"""Adding people from an Excel file (Settings > Users; owner request, 24 Nov 2026): the template, the row-by-row check
that writes nothing, the all-or-nothing import (each person audited), directory sign-in, and who may do it."""
from __future__ import annotations

import io
import zipfile

from sqlalchemy import func, select

from app.core import xlsx
from app.core.xlsx_read import read_rows
from app.extensions import db
from app.models import AppUser, AuditEvent
from tests.conftest import Api
from tests.integration.test_ldap import BG_PASSWORD, BREAK_GLASS, fake_dir, ldap_app  # noqa: F401 (fixtures)

API = "/api/v1/users"
HEADINGS = ["Username (U number)", "Full name", "Role", "Groups (roles tied to groups only)", "Password"]


def _book(rows, headings=HEADINGS) -> bytes:
    sheet = xlsx.Sheet("Users")
    sheet.add(headings)
    for row in rows:
        sheet.add(list(row))
    return xlsx.workbook([sheet])


def _send(api: Api, path: str, data: bytes, name="people.xlsx"):
    return api.client.post(f"{API}/{path}", data={"file": (io.BytesIO(data), name)}, content_type="multipart/form-data",
                           headers={"X-CSRF-Token": api.csrf})


def _users(app) -> int:
    with app.app_context():
        return db.session().scalar(select(func.count()).select_from(AppUser))


def _codes(row: dict, kind="problems") -> list[str]:
    return [p["code"] for p in row[kind]]


def test_the_template_has_the_headings_a_role_list_and_the_instructions(admin):
    res = admin.get(f"{API}/import-template?lang=ar")
    assert res.status_code == 200 and res.headers["Content-Disposition"].endswith('cpc-users-template-ar.xlsx"')
    rows = read_rows(res.data, "t.xlsx")
    assert rows[0][1] == ["اسم المستخدم (رقم U)", "الاسم الكامل", "الدور", "المجاميع (للأدوار المقيّدة بمجاميع فقط)",
                          "كلمة المرور"]
    book = zipfile.ZipFile(io.BytesIO(res.data))
    sheets = [n for n in book.namelist() if n.startswith("xl/worksheets/sheet")]
    assert len(sheets) == 3 and b"<dataValidation" in book.read("xl/worksheets/sheet1.xml")
    assert "مدير النظام".encode() in book.read("xl/worksheets/sheet3.xml")  # the role list, in Arabic
    english = read_rows(admin.get(f"{API}/import-template?lang=en").data, "t.xlsx")
    assert english[0][1] == HEADINGS


def test_every_row_is_checked_and_nothing_is_written(app, admin):
    before = _users(app)
    data = _book([
        ("it.one", "IT One", "Viewer", "", "Long-Password-1"),               # fine
        ("it.two", "IT Two", "Nobody", "", "Long-Password-1"),               # unknown role
        ("it.three", "IT Three", "DEPT_HEAD", "", "Long-Password-1"),        # a group-scoped role without groups
        ("mock.exec", "Exists", "مطّلع", "", "Long-Password-1"),             # already a user (Arabic role name)
        ("it.five", "IT Five", "VIEWER", "", "short"),                       # password too short
        ("IT.ONE", "Again", "VIEWER", "", "Long-Password-1"),                # twice in the file
        ("it.seven", "IT Seven", "Executive leadership", "G1", "Long-Password-1"),  # groups ignored (sees all)
        ("it.eight", "IT Eight", "DEPT_HEAD", "G1, Nowhere", "Long-Password-1"),     # unknown group
    ])
    res = _send(admin, "import/check", data)
    assert res.status_code == 200, res.get_json()
    body = res.get_json()
    by_name = {r["username"]: r for r in body["rows"]}
    assert _codes(by_name["it.one"]) == [] and by_name["it.one"]["role"]["code"] == "VIEWER"
    assert _codes(by_name["it.two"]) == ["ROLE_UNKNOWN"]
    assert _codes(by_name["it.three"]) == ["GROUPS_NEEDED"]
    assert _codes(by_name["mock.exec"]) == ["USERNAME_EXISTS"]
    assert _codes(by_name["it.five"]) == ["PASSWORD_SHORT"]
    assert _codes(by_name["IT.ONE"]) == ["USERNAME_TWICE"] and by_name["IT.ONE"]["problems"][0]["row"] == 2
    assert _codes(by_name["it.seven"]) == [] and _codes(by_name["it.seven"], "warnings") == ["GROUPS_IGNORED"]
    assert by_name["it.eight"]["problems"] == [{"code": "GROUP_UNKNOWN", "value": "Nowhere"}]
    assert body["total"] == 8 and body["ready"] == 2 and body["canImport"] is False
    assert "Long-Password-1" not in res.get_data(as_text=True)  # passwords never come back
    assert _users(app) == before


def test_importing_adds_everyone_in_one_transaction_and_audits_each(app, admin):
    before = _users(app)
    data = _book([
        ("it.one", "IT One", "مطّلع", "", "Long-Password-1"),
        ("it.head", "IT Head", "رئيس المجموعة", "مجموعة 1، G2", "Long-Password-2"),
        ("it.demo", "", "VIEWER", "", ""),  # the demo password, the username as the name
    ])
    checked = _send(admin, "import/check", data).get_json()
    assert checked["canImport"] and _codes(checked["rows"][2], "warnings") == ["DEMO_PASSWORD"]
    res = _send(admin, "import", data)
    assert res.status_code == 200, res.get_json()
    assert res.get_json()["added"] == 3 and _users(app) == before + 3
    head = admin.json(f"{API}?q=it.head")["items"][0]
    assert head["role"] == "DEPT_HEAD" and sorted(d["code"] for d in head["departments"]) == ["G1", "G2"]
    with app.app_context():
        reasons = db.session().scalars(select(AuditEvent.reason).where(
            AuditEvent.entity_type == "APP_USER", AuditEvent.action == "CREATE",
            AuditEvent.reason.like("Added from an Excel file%"))).all()
    assert sorted(reasons) == [f"Added from an Excel file (row {n})" for n in (2, 3, 4)]
    signed_in = app.test_client().post("/api/v1/session", json={"username": "it.head", "password": "Long-Password-2"})
    assert signed_in.status_code == 200
    again = _send(admin, "import", data)
    assert again.status_code == 409 and again.get_json()["code"] == "IMPORT_HAS_PROBLEMS"  # now they exist


def test_nobody_is_added_while_a_row_has_a_problem(app, admin):
    before = _users(app)
    res = _send(admin, "import", _book([("it.ok", "OK", "VIEWER", "", "Long-Password-1"),
                                        ("it.bad", "Bad", "Nobody", "", "Long-Password-1")]))
    assert res.status_code == 409 and res.get_json()["code"] == "IMPORT_HAS_PROBLEMS"
    assert _users(app) == before


def test_a_file_without_the_headings_or_not_a_workbook_is_refused(admin):
    res = _send(admin, "import/check", _book([("x", "y")], headings=["Name", "Something"]))
    assert res.status_code == 400 and res.get_json()["fieldErrors"][0]["field"] == "file"
    assert _send(admin, "import/check", b"not a workbook", "people.xlsx").status_code == 400
    csv = "اسم المستخدم,الاسم الكامل,الدور,المجاميع,كلمة المرور\nit.csv,من ملف,VIEWER,,Long-Password-1\n".encode()
    body = _send(admin, "import/check", csv, "people.csv").get_json()
    assert body["canImport"] and body["rows"][0]["displayName"] == "من ملف"


def test_only_a_system_administrator_may_import(app, executive):
    assert executive.get(f"{API}/import-template").status_code == 403
    assert _send(executive, "import/check", _book([])).status_code == 403
    assert _send(executive, "import", _book([])).status_code == 403


def test_with_directory_sign_in_the_username_is_the_windows_name_and_no_password_is_kept(ldap_app):
    admin = Api(ldap_app, None)
    admin.login(BREAK_GLASS, BG_PASSWORD)
    data = _book([("u55555", "Not In App", "VIEWER", "", "Ignored-Pass-1"),
                  ("jsmith", "J Smith", "VIEWER", "", "")])
    body = _send(admin, "import/check", data).get_json()
    first, second = body["rows"]
    assert first["username"] == "U55555" and first["password"] == "DIRECTORY"
    assert _codes(first, "warnings") == ["PASSWORD_IGNORED"] and _codes(second) == ["NOT_WINDOWS_NAME"]
    res = _send(admin, "import", _book([("u55555", "Not In App", "VIEWER", "", "Ignored-Pass-1")]))
    assert res.status_code == 200 and res.get_json()["users"][0]["username"] == "U55555"
    from werkzeug.security import check_password_hash
    with ldap_app.app_context():
        user = db.session().scalar(select(AppUser).where(AppUser.username == "U55555"))
        assert user is not None and not check_password_hash(user.password_hash, "Ignored-Pass-1")  # never kept
