"""Sign-in through the company directory (AUTH_MODE=ldap), offline: ldap3's built-in MOCK_SYNC server stands in for
Active Directory through app.config["DIRECTORY_CONNECTION_FACTORY"]. No network is used.

The mock directory (OU=Staff,DC=company,DC=local):
  U12345 Jane Smith   - added in the app as SYS_ADMIN
  U22222 Ali Hassan   - (in a sub-OU) added as DEPT_HEAD on Group 1 and Group 2
  U33333 Carl Chief   - added as EXECUTIVE
  U44444 Tara Top     - added as CAPABILITY_MGR
  U55555 Not In App   - in the directory only (option A: not allowed in)
  U66666              - two directory entries with this name (refused)
  U77777 Gone Away    - added, then deactivated in the app
plus the read-only service account. The app also has the seeded demo users (mock.admin, mock.exec, ...) and the
break-glass SYS_ADMIN cpc.breakglass.
"""
from __future__ import annotations

import getpass
import ssl

import pytest
from ldap3 import MOCK_SYNC, MODIFY_DELETE, MODIFY_REPLACE, OFFLINE_AD_2012_R2, Connection, Server
from ldap3.core.exceptions import LDAPSocketOpenError
from sqlalchemy import func, select

from app.core.database import write_intent
from app.extensions import db
from app.models import ROLE_SYS_ADMIN, AppSession, AppUser, AuditEvent
from app.security import directory as directory_module
from app.security.auth import hash_password
from app.security.directory import Directory
from app.security.mock_credentials import MOCK_PASSWORD
from app.services import user_service
from tests.conftest import Api, _app_from

API = "/api/v1"
BASE = "OU=Staff,DC=company,DC=local"
SVC = "CN=svc-cpc,OU=Service,DC=company,DC=local"
SVC_PASSWORD = "Svc-Secret-Pass-9"
BREAK_GLASS = "cpc.breakglass"
BG_PASSWORD = "Emergency-Pass-123456"
LOGIN_FAILED = "Invalid username or password."
UNAVAILABLE = "The company directory cannot be reached. Try again in a few minutes or contact IT."
COOKIE = "cpc_sid"
G1, G2, G3, G4 = 1, 2, 3, 4  # department ids in the seeded demo

JANE = ("U12345", "Jane#Pass(1)*")
ALI = ("U22222", "Ali-Pass-2")
CARL = ("U33333", "Carl-Pass-3")
TARA = ("U44444", "Tara-Pass-4")
NOT_IN_APP = ("U55555", "Nobody-Pass-5")
TWICE = ("U66666", "Twice-Pass-6")
GONE = ("U77777", "Gone-Pass-7")

DIRECTORY_PEOPLE = [
    (f"CN=Jane Smith,{BASE}", "U12345", "Jane Smith", JANE[1]),
    (f"CN=Ali Hassan,OU=Engineers,{BASE}", "U22222", "Ali Hassan", ALI[1]),
    (f"CN=Carl Chief,{BASE}", "U33333", "Carl Chief", CARL[1]),
    (f"CN=Tara Top,{BASE}", "U44444", "Tara Top", TARA[1]),
    (f"CN=Not In App,{BASE}", "U55555", "Not In App", NOT_IN_APP[1]),
    (f"CN=Twice One,{BASE}", "U66666", "Twice One", TWICE[1]),
    (f"CN=Twice Two,OU=Engineers,{BASE}", "U66666", "Twice Two", TWICE[1]),
    (f"CN=Gone Away,{BASE}", "U77777", "Gone Away", GONE[1]),
]

LDAP = dict(auth_mode="ldap", ldap_servers=("dc01.company.local",), ldap_base_dn=BASE, ldap_bind_dn=SVC,
            ldap_bind_password=SVC_PASSWORD, break_glass_username=BREAK_GLASS)


class FakeDirectory:
    """A MOCK_SYNC Active Directory that records every connection, bind and search the app makes."""

    def __init__(self, with_base=True):
        self.server = Server("dc01.company.local", get_info=OFFLINE_AD_2012_R2)
        self.connections: list[str] = []  # who each new connection was opened for
        self.binds: list[str] = []
        self.filters: list[str] = []
        self.down = False
        boot = Connection(self.server, user=SVC, password=SVC_PASSWORD, client_strategy=MOCK_SYNC)
        if with_base:
            boot.strategy.add_entry(BASE, {"objectClass": ["top", "organizationalUnit"], "ou": "Staff"})
        boot.strategy.add_entry(SVC, {"userPassword": SVC_PASSWORD, "objectClass": ["top", "person", "user"],
                                      "sAMAccountName": "svc-cpc"})
        for dn, sam, name, password in DIRECTORY_PEOPLE:
            boot.strategy.add_entry(dn, {"userPassword": password, "objectClass": ["top", "person", "user"],
                                         "sAMAccountName": sam, "displayName": name})

    def factory(self, user, password):
        self.connections.append(user)
        if self.down:
            raise LDAPSocketOpenError("socket connection error while opening: [WinError 10060] timed out")
        fake = self

        class Recording(Connection):
            def bind(self, *args, **kwargs):
                fake.binds.append(self.user)
                return super().bind(*args, **kwargs)

            def search(self, search_base, search_filter, *args, **kwargs):
                fake.filters.append(search_filter)
                return super().search(search_base, search_filter, *args, **kwargs)

        return Recording(self.server, user=user, password=password, client_strategy=MOCK_SYNC, raise_exceptions=False)

    def set_display_name(self, dn, name):
        """IT changes (or, with None, clears) a person's display name in the directory."""
        conn = Connection(self.server, user=SVC, password=SVC_PASSWORD, client_strategy=MOCK_SYNC)
        conn.bind()
        change = [(MODIFY_REPLACE, [name])] if name is not None else [(MODIFY_DELETE, [])]
        assert conn.modify(dn, {"displayName": change}), conn.result

    def reset(self):
        self.connections.clear()
        self.binds.clear()
        self.filters.clear()

    @property
    def untouched(self) -> bool:
        return not (self.connections or self.binds or self.filters)


def _sign_in(app, username, password):
    return app.test_client().post(f"{API}/session", json={"username": username, "password": password})


def _login_failed(res):
    assert res.status_code == 401, (res.status_code, res.get_json())
    body = res.get_json()
    assert body["code"] == "LOGIN_FAILED" and body["message"] == LOGIN_FAILED, body
    assert "Set-Cookie" not in res.headers or f"{COOKIE}=;" in res.headers["Set-Cookie"]


def _err(res, status, code, field=None):
    assert res.status_code == status, (res.status_code, res.get_json())
    body = res.get_json()
    assert body["code"] == code, body
    if field is not None:
        assert [e["field"] for e in body["fieldErrors"]] == [field], body
    return body


def _ok(api: Api, method: str, url: str, json=None, status=200):
    """Send a request (with the CSRF header) and expect `status`; returns the JSON body."""
    if method == "get":
        res = api.get(url)
    else:
        res = getattr(api, method)(url, json=json)
    assert res.status_code == status, (res.status_code, res.get_json(silent=True))
    return res.get_json()


def _count(app, model) -> int:
    with app.app_context():
        return db.session().scalar(select(func.count()).select_from(model))


def _user(app, username) -> AppUser | None:
    with app.app_context():
        return db.session().scalar(select(AppUser).where(func.lower(AppUser.username) == username.lower()))


def _audit_rows(app, user_id) -> list[AuditEvent]:
    with app.app_context():
        return list(db.session().scalars(select(AuditEvent).where(
            AuditEvent.entity_type == "APP_USER", AuditEvent.entity_id == user_id).order_by(AuditEvent.id)))


def _set_break_glass(app, password=BG_PASSWORD):
    with app.app_context(), write_intent():
        return user_service.set_break_glass_password(password)


@pytest.fixture
def fake_dir():
    return FakeDirectory()


def _ldap_app(template, tmp_path, fake_dir, **overrides):
    application = _app_from(template, tmp_path, **{**LDAP, **overrides})
    application.config["DIRECTORY_CONNECTION_FACTORY"] = fake_dir.factory
    return application


@pytest.fixture
def ldap_app(seeded_template, tmp_path, fake_dir):
    """The seeded demo database in directory mode, with the break-glass SYS_ADMIN and the people of the mock directory
    added through Users & access."""
    application = _ldap_app(seeded_template, tmp_path, fake_dir)
    _set_break_glass(application)
    bg = Api(application, None)
    bg.login(BREAK_GLASS, BG_PASSWORD)
    for username, display, role, departments in (
        ("U12345", "Jane Smith", "SYS_ADMIN", []),
        ("U22222", "Ali Hassan", "DEPT_HEAD", [str(G1), str(G2)]),
        ("U33333", "Carl Chief", "EXECUTIVE", []),
        ("U44444", "Tara Top", "CAPABILITY_MGR", []),
        ("U66666", "Twice", "EXECUTIVE", []),
        ("U77777", "Gone Away", "EXECUTIVE", []),
    ):
        _ok(bg, "post", f"{API}/users", {"username": username, "displayName": display, "role": role,
                                         "departmentIds": departments}, status=201)
    gone = _user(application, "U77777")
    _ok(bg, "patch", f"{API}/users/{gone.id}", {"active": False, "reason": "Left the company"})
    application.config["LOGIN_THROTTLE"].clear()
    fake_dir.reset()
    yield application
    db.dispose()


@pytest.fixture
def jane(ldap_app, fake_dir) -> Api:
    """U12345, a SYS_ADMIN who signs in with the company directory."""
    api = Api(ldap_app, None)
    api.login(*JANE)
    fake_dir.reset()
    return api


def _first_id(api: Api, url: str) -> str:
    """The id of the first record a list answers (as the given user sees it)."""
    body = _ok(api, "get", url)
    items = body["items"]
    assert items, (url, body)
    return items[0]["id"]


# ---------------------------------------------------------------- a good sign-in

def test_a_good_password_signs_in_with_the_apps_role_and_departments(ldap_app, fake_dir):
    api = Api(ldap_app, None)
    res = api.login(*ALI)
    body = res.get_json()
    assert body["user"]["username"] == "U22222" and body["user"]["displayName"] == "Ali Hassan"
    assert body["user"]["role"] == "DEPT_HEAD" and body["user"]["departmentIds"] == ["1", "2"]  # from the app
    assert "admin" not in body["user"]["permissions"]
    assert body["authMode"] == "ldap"
    assert f"{COOKIE}=" in res.headers["Set-Cookie"] and "HttpOnly" in res.headers["Set-Cookie"]
    # The service account looks the person up, then a NEW connection signs in as that person's DN.
    assert fake_dir.connections == [SVC, f"CN=Ali Hassan,OU=Engineers,{BASE}"]
    assert fake_dir.binds == [SVC, f"CN=Ali Hassan,OU=Engineers,{BASE}"]
    assert fake_dir.filters == ["(&(objectClass=user)(sAMAccountName=U22222))"]
    session = _ok(api, "get", f"{API}/session")
    assert session["authMode"] == "ldap" and session["user"]["role"] == "DEPT_HEAD"


def test_the_department_scope_is_the_apps(ldap_app, jane):
    """A DEPT_HEAD on Group 1 and Group 2 signed in through the directory sees and changes only those departments;
    records elsewhere answer 404, as if they did not exist."""
    ali = Api(ldap_app, None)
    ali.login(*ALI)
    in_scope = _first_id(jane, f"{API}/assets?department={G2}")
    out_of_scope = _first_id(jane, f"{API}/assets?department={G3}")
    assert _ok(ali, "get", f"{API}/assets/{in_scope}")["id"] == in_scope
    _err(ali.get(f"{API}/assets/{out_of_scope}"), 404, "NOT_FOUND")
    everything = _ok(jane, "get", f"{API}/assets")["totalItems"]
    seen = _ok(ali, "get", f"{API}/assets")["totalItems"]
    mine = sum(_ok(jane, "get", f"{API}/assets?department={d}")["totalItems"] for d in (G1, G2))
    assert 0 < seen == mine < everything
    assert _ok(ali, "get", f"{API}/assets?department={G4}")["totalItems"] == 0
    # Changes: allowed in Group 2, 404 in Group 3.
    req_g2 = _first_id(jane, f"{API}/requirements?department={G2}")
    req_g3 = _first_id(jane, f"{API}/requirements?department={G3}")
    assert _ok(ali, "patch", f"{API}/requirements/{req_g2}", {"notes": "Checked by Ali", "reason": "Review"})[
        "notes"] == "Checked by Ali"
    _err(ali.patch(f"{API}/requirements/{req_g3}", json={"notes": "Not mine", "reason": "Review"}), 404, "NOT_FOUND")


@pytest.mark.parametrize("typed", ["U12345", "u12345", "COMPANY\\u12345", " u12345@company.local ", "company\\U12345"])
def test_every_way_of_typing_the_windows_username_works(ldap_app, typed):
    res = _sign_in(ldap_app, typed, JANE[1])
    assert res.status_code == 200, res.get_json()
    assert res.get_json()["user"]["username"] == "U12345" and res.get_json()["user"]["role"] == "SYS_ADMIN"


@pytest.mark.parametrize("account, role", [(CARL, "EXECUTIVE"), (TARA, "CAPABILITY_MGR"), (JANE, "SYS_ADMIN")])
def test_every_role_comes_from_the_app(ldap_app, account, role):
    res = _sign_in(ldap_app, *account)
    assert res.status_code == 200 and res.get_json()["user"]["role"] == role
    assert res.get_json()["user"]["departmentIds"] is None  # ALL-scoped roles


def test_a_role_change_in_the_app_applies_at_the_next_sign_in(ldap_app, jane):
    carl = _user(ldap_app, "U33333")
    _ok(jane, "patch", f"{API}/users/{carl.id}", {"role": "CAPABILITY_MGR", "reason": "Promoted"})
    assert _sign_in(ldap_app, *CARL).get_json()["user"]["role"] == "CAPABILITY_MGR"


def test_a_viewer_signed_in_through_the_directory_cannot_write(ldap_app, jane):
    carl = _user(ldap_app, "U33333")
    _ok(jane, "patch", f"{API}/users/{carl.id}", {"role": "VIEWER", "reason": "Read only"})
    viewer = Api(ldap_app, None)
    viewer.login(*CARL)
    req = _first_id(jane, f"{API}/requirements")
    _err(viewer.patch(f"{API}/requirements/{req}", json={"notes": "x", "reason": "x"}), 403, "FORBIDDEN")


# ---------------------------------------------------------------- the name follows the directory

def test_a_new_name_in_the_directory_is_taken_at_the_next_sign_in(ldap_app, fake_dir):
    ali = _user(ldap_app, "U22222")
    rows_before = len(_audit_rows(ldap_app, ali.id))
    fake_dir.set_display_name(f"CN=Ali Hassan,OU=Engineers,{BASE}", "  Ali   Hassan Al Marri ")
    body = _sign_in(ldap_app, *ALI).get_json()
    assert body["user"]["displayName"] == "Ali Hassan Al Marri"  # spaces tidied
    assert body["user"]["role"] == "DEPT_HEAD" and body["user"]["departmentIds"] == ["1", "2"]  # still the app's
    after = _user(ldap_app, "U22222")
    assert after.display_name == "Ali Hassan Al Marri" and after.version == ali.version + 1
    rows = _audit_rows(ldap_app, ali.id)
    assert len(rows) == rows_before + 1
    event = rows[-1]
    assert (event.action, event.actor_id, event.reason) == ("UPDATE", ali.id, "Name updated from the company "
                                                                              "directory at sign-in")
    assert '"display_name": "Ali Hassan"' in event.before_json
    assert '"display_name": "Ali Hassan Al Marri"' in event.after_json
    assert f'"version": {ali.version + 1}' in event.after_json
    assert '"department_ids_text": "1,2"' in event.after_json  # the departments are not touched
    assert "password" not in f"{event.before_json} {event.after_json}".lower()
    # Signing in again with the same name changes nothing and writes no history.
    assert _sign_in(ldap_app, *ALI).status_code == 200
    assert len(_audit_rows(ldap_app, ali.id)) == rows_before + 1
    assert _user(ldap_app, "U22222").version == ali.version + 1


def test_the_name_change_shows_in_the_audit_list(ldap_app, fake_dir, jane):
    ali = _user(ldap_app, "U22222")
    fake_dir.set_display_name(f"CN=Ali Hassan,OU=Engineers,{BASE}", "Ali H. Al Marri")
    assert _sign_in(ldap_app, *ALI).status_code == 200
    events = _ok(jane, "get", f"{API}/audit?entityType=APP_USER&entityId={ali.id}")["items"]
    latest = events[0]
    assert latest["action"] == "UPDATE" and latest["actor"]["id"] == str(ali.id)
    assert latest["reason"] == "Name updated from the company directory at sign-in"
    assert {"field": "display_name", "from": "Ali Hassan", "to": "Ali H. Al Marri"} in latest["changes"]


def test_a_name_typed_in_the_app_gives_way_to_the_directory_at_the_next_sign_in(ldap_app, jane):
    tara = _user(ldap_app, "U44444")
    _ok(jane, "patch", f"{API}/users/{tara.id}", {"displayName": "T. Top", "reason": "Nickname"})
    assert _sign_in(ldap_app, *TARA).get_json()["user"]["displayName"] == "Tara Top"
    assert _user(ldap_app, "U44444").display_name == "Tara Top"


def test_a_directory_entry_without_a_display_name_keeps_the_apps_name(ldap_app, fake_dir):
    fake_dir.set_display_name(f"CN=Carl Chief,{BASE}", None)
    carl = _user(ldap_app, "U33333")
    rows_before = len(_audit_rows(ldap_app, carl.id))
    assert _sign_in(ldap_app, *CARL).get_json()["user"]["displayName"] == "Carl Chief"  # never "U33333"
    assert len(_audit_rows(ldap_app, carl.id)) == rows_before


def test_the_name_is_not_taken_without_a_sign_in(ldap_app, fake_dir):
    """A wrong password, or an account deactivated in the app, changes nothing."""
    fake_dir.set_display_name(f"CN=Jane Smith,{BASE}", "Jane Doe")
    _login_failed(_sign_in(ldap_app, JANE[0], "wrong-password"))
    assert _user(ldap_app, "U12345").display_name == "Jane Smith"
    fake_dir.set_display_name(f"CN=Gone Away,{BASE}", "Gone Elsewhere")
    _login_failed(_sign_in(ldap_app, *GONE))
    assert _user(ldap_app, "U77777").display_name == "Gone Away"


def test_the_break_glass_account_keeps_its_name(ldap_app):
    res = _sign_in(ldap_app, BREAK_GLASS, BG_PASSWORD)
    assert res.status_code == 200 and res.get_json()["user"]["displayName"] == "Emergency admin"


# ---------------------------------------------------------------- refused sign-ins (always the same answer)

def test_a_wrong_password_is_refused_by_the_directory(ldap_app, fake_dir):
    _login_failed(_sign_in(ldap_app, JANE[0], "Jane#Pass(1)"))
    assert fake_dir.binds == [SVC, f"CN=Jane Smith,{BASE}"]  # the directory was asked and said no


@pytest.mark.parametrize("password", ["", " ", "   ", "\t", "\n "])
def test_an_empty_or_blank_password_never_reaches_the_directory(ldap_app, fake_dir, password):
    """An empty simple bind can be an anonymous bind that 'succeeds' (RFC 4513): it is never sent."""
    _login_failed(_sign_in(ldap_app, JANE[0], password))
    assert fake_dir.untouched


def test_an_unknown_windows_username_is_refused(ldap_app, fake_dir):
    _login_failed(_sign_in(ldap_app, "U99999", "Whatever-1"))
    assert fake_dir.binds == [SVC]  # looked up, not found: no user bind


def test_option_a_people_in_the_directory_but_not_added_in_the_app_are_refused(ldap_app, fake_dir):
    _login_failed(_sign_in(ldap_app, *NOT_IN_APP))
    assert fake_dir.binds == [SVC, f"CN=Not In App,{BASE}"]  # right password, but nobody added them
    assert _user(ldap_app, "U55555") is None  # and no account is created on the fly


def test_people_deactivated_in_the_app_are_refused(ldap_app):
    _login_failed(_sign_in(ldap_app, *GONE))


def test_deactivating_someone_ends_their_session_at_once(ldap_app, jane):
    ali = Api(ldap_app, None)
    ali.login(*ALI)
    assert ali.get(f"{API}/session").status_code == 200
    _ok(jane, "patch", f"{API}/users/{_user(ldap_app, 'U22222').id}", {"active": False, "reason": "Left"})
    assert ali.get(f"{API}/session").status_code == 401
    _login_failed(_sign_in(ldap_app, *ALI))


def test_two_directory_entries_for_one_username_are_refused(ldap_app, fake_dir):
    _login_failed(_sign_in(ldap_app, *TWICE))
    assert fake_dir.binds == [SVC]  # never guesses which of the two to sign in as


@pytest.mark.parametrize("typed", [
    "U1*", "*", "U*)(objectClass=*", "*)(sAMAccountName=*", "U12345)(|(sAMAccountName=*", "U12345*", "U1\\2a",
    "U12345\x00", "(U12345)", "U12345 OR 1=1",
])
def test_filter_injection_attempts_are_refused_before_the_directory(ldap_app, fake_dir, typed):
    _login_failed(_sign_in(ldap_app, typed, JANE[1]))
    assert fake_dir.untouched  # none of these is "U followed by digits"


@pytest.mark.parametrize("typed", ["U1*", "U*)(objectClass=*", "U12345)(|(sAMAccountName=*", "U*"])
def test_filter_characters_are_escaped_even_when_the_pattern_lets_them_through(ldap_app, fake_dir, typed):
    """A looser LDAP_USERNAME_PATTERN must still not let * ( ) \\ change the search."""
    ldap_app.config["SETTINGS"].ldap_username_pattern = r"^U.+$"
    with ldap_app.app_context():
        assert directory_module.get_directory().authenticate(typed, JANE[1]) is None
    assert fake_dir.binds == [SVC]  # nothing matched: the typed password was never tried against Jane
    assert len(fake_dir.filters) == 1
    searched = fake_dir.filters[0]
    value = searched.removeprefix("(&(objectClass=user)(sAMAccountName=").removesuffix("))")
    assert "*" not in value and "(" not in value and ")" not in value, searched
    assert "\\2a" in value


@pytest.mark.parametrize("username", ["mock.admin", "mock.exec", "mock.head", "mock.viewer", "MOCK.ADMIN"])
def test_local_and_mock_accounts_cannot_sign_in(ldap_app, fake_dir, username):
    """The seeded accounts' stored (public mock) password is never used in directory mode."""
    _login_failed(_sign_in(ldap_app, username, MOCK_PASSWORD))
    assert fake_dir.untouched


def test_a_directory_users_local_password_is_ignored(ldap_app, fake_dir):
    with ldap_app.app_context(), write_intent():
        jane_row = user_service.find("U12345")
        jane_row.password_hash = hash_password("Local-Only-Pass-1")
        db.session().commit()
    _login_failed(_sign_in(ldap_app, "U12345", "Local-Only-Pass-1"))
    assert fake_dir.binds == [SVC, f"CN=Jane Smith,{BASE}"]  # only the directory decides
    assert _sign_in(ldap_app, *JANE).status_code == 200


def test_the_same_message_for_every_refusal(ldap_app):
    bodies = [_sign_in(ldap_app, u, p).get_json() for u, p in (
        ("U12345", "wrong"), ("U12345", ""), ("U99999", "x"), NOT_IN_APP, GONE, TWICE, ("jsmith", "x"),
        ("mock.admin", MOCK_PASSWORD), (BREAK_GLASS, "wrong-wrong-wrong-1"))]
    assert {(b["code"], b["message"]) for b in bodies} == {("LOGIN_FAILED", LOGIN_FAILED)}


# ---------------------------------------------------------------- the directory is down

def _session_rows(app) -> int:
    return _count(app, AppSession)


def test_an_unreachable_directory_answers_503_and_writes_nothing(ldap_app, fake_dir):
    fake_dir.down = True
    sessions, audits = _session_rows(ldap_app), _count(ldap_app, AuditEvent)
    res = _sign_in(ldap_app, *JANE)
    assert res.status_code == 503
    body = res.get_json()
    assert body["code"] == "DIRECTORY_UNAVAILABLE" and body["message"] == UNAVAILABLE
    text = res.get_data(as_text=True)
    assert "WinError" not in text and "dc01" not in text and SVC_PASSWORD not in text  # details stay in the log
    assert "Set-Cookie" not in res.headers
    assert _session_rows(ldap_app) == sessions and _count(ldap_app, AuditEvent) == audits


def test_the_technical_cause_is_logged_without_the_password(ldap_app, fake_dir, caplog):
    fake_dir.down = True
    with caplog.at_level("ERROR", logger="cpc.auth"):
        _sign_in(ldap_app, *JANE)
    records = [r for r in caplog.records if r.getMessage() == "company directory unavailable at sign-in"]
    assert len(records) == 1
    fields = records[0].fields
    assert fields["username"] == "U12345" and "timed out" in fields["error"] and fields["hint"]
    assert all(JANE[1] not in str(r.__dict__) for r in caplog.records)


def test_an_outage_does_not_lock_people_out(ldap_app, fake_dir):
    fake_dir.down = True
    statuses = {_sign_in(ldap_app, *JANE).status_code for _ in range(25)}
    assert statuses == {503}  # never 429: nobody's password was checked
    fake_dir.down = False
    assert _sign_in(ldap_app, *JANE).status_code == 200


def test_a_refused_service_account_is_an_outage_not_a_wrong_password(ldap_app, fake_dir):
    ldap_app.config["SETTINGS"].ldap_bind_password = "not-the-service-password"
    res = _sign_in(ldap_app, *JANE)
    assert res.status_code == 503 and res.get_json()["code"] == "DIRECTORY_UNAVAILABLE"
    assert fake_dir.binds == [SVC]  # Jane's password was never tried


def test_a_missing_search_base_is_an_outage(seeded_template, tmp_path):
    fake = FakeDirectory(with_base=False)
    application = _ldap_app(seeded_template, tmp_path, fake, ldap_base_dn="OU=Nowhere,DC=company,DC=local")
    try:
        res = _sign_in(application, *JANE)
        assert res.status_code == 503 and res.get_json()["code"] == "DIRECTORY_UNAVAILABLE"
    finally:
        db.dispose()


def test_the_throttle_still_stops_password_guessing(ldap_app, fake_dir):
    codes = [_sign_in(ldap_app, "U12345", f"guess-{i}").status_code for i in range(6)]
    assert codes == [401] * 5 + [429]
    # The throttle key is the normalised name: another spelling of the same person is blocked too.
    assert _sign_in(ldap_app, "company\\u12345", JANE[1]).status_code == 429
    fake_dir.reset()
    assert _sign_in(ldap_app, "U12345", JANE[1]).status_code == 429 and fake_dir.untouched


def test_earlier_failures_still_count_after_an_outage(ldap_app, fake_dir):
    for i in range(4):
        _login_failed(_sign_in(ldap_app, "U12345", f"guess-{i}"))
    fake_dir.down = True
    assert _sign_in(ldap_app, "U12345", "guess-x").status_code == 503
    fake_dir.down = False
    assert _sign_in(ldap_app, "U12345", "guess-5").status_code == 401
    assert _sign_in(ldap_app, "U12345", "guess-6").status_code == 429


# ---------------------------------------------------------------- the break-glass admin

def test_break_glass_signs_in_with_its_local_password_and_never_asks_the_directory(ldap_app, fake_dir, caplog):
    with caplog.at_level("WARNING", logger="cpc.auth"):
        res = _sign_in(ldap_app, "CPC.BreakGlass", BG_PASSWORD)
    assert res.status_code == 200
    user = res.get_json()["user"]
    assert user["username"] == BREAK_GLASS and user["role"] == "SYS_ADMIN" and "admin" in user["permissions"]
    assert fake_dir.untouched
    warnings = [r for r in caplog.records if r.getMessage() == "break-glass sign-in"]
    assert len(warnings) == 1 and warnings[0].fields == {"username": BREAK_GLASS, "clientIp": "127.0.0.1"}
    assert BG_PASSWORD not in str(warnings[0].__dict__)


def test_a_wrong_break_glass_password_is_refused_and_logged(ldap_app, fake_dir, caplog):
    with caplog.at_level("WARNING", logger="cpc.auth"):
        _login_failed(_sign_in(ldap_app, BREAK_GLASS, "Not-The-Right-One-123"))
    assert fake_dir.untouched
    assert [r.getMessage() for r in caplog.records].count("break-glass sign-in failed") == 1


def test_break_glass_works_while_the_directory_is_down(ldap_app, fake_dir):
    fake_dir.down = True
    assert _sign_in(ldap_app, *JANE).status_code == 503
    assert _sign_in(ldap_app, BREAK_GLASS, BG_PASSWORD).status_code == 200
    assert fake_dir.connections == [SVC]  # only Jane's attempt tried to connect


def test_with_break_glass_switched_off_the_account_cannot_sign_in(ldap_app, fake_dir):
    ldap_app.config["SETTINGS"].break_glass_username = None  # BREAK_GLASS_USERNAME left empty
    _login_failed(_sign_in(ldap_app, BREAK_GLASS, BG_PASSWORD))
    assert fake_dir.untouched


def test_a_deactivated_break_glass_account_cannot_sign_in(ldap_app, jane):
    bg = _user(ldap_app, BREAK_GLASS)
    _ok(jane, "patch", f"{API}/users/{bg.id}", {"active": False, "reason": "Sealed again"})
    _login_failed(_sign_in(ldap_app, BREAK_GLASS, BG_PASSWORD))


def test_a_break_glass_account_that_is_no_longer_a_sys_admin_cannot_sign_in(ldap_app, jane):
    bg = _user(ldap_app, BREAK_GLASS)
    _ok(jane, "patch", f"{API}/users/{bg.id}", {"role": "EXECUTIVE", "reason": "Demoted"})
    _login_failed(_sign_in(ldap_app, BREAK_GLASS, BG_PASSWORD))


def test_a_break_glass_password_not_set_by_the_server_command_is_refused(seeded_template, tmp_path, fake_dir):
    """In directory mode the break-glass password only counts once set-break-glass-password set it (audited on the
    account itself): a hash written any other way, e.g. a local-mode account of that name, is not enough."""
    local = _app_from(seeded_template, tmp_path)  # AUTH_MODE=local, break-glass switched off
    try:
        admin = Api(local, "mock.admin")
        _ok(admin, "post", f"{API}/users", {"username": BREAK_GLASS, "role": "SYS_ADMIN", "password": BG_PASSWORD},
            status=201)
    finally:
        db.dispose()
    target = tmp_path / "ldap"  # the same database, now in directory mode with the break-glass name switched on
    target.mkdir()
    application = _ldap_app(tmp_path / "test.db", target, fake_dir)
    try:
        _login_failed(_sign_in(application, BREAK_GLASS, BG_PASSWORD))
        assert fake_dir.untouched
    finally:
        db.dispose()


# ---------------------------------------------------------------- flask set-break-glass-password

def _prompts(monkeypatch, *answers):
    replies = iter(answers)
    monkeypatch.setattr(getpass, "getpass", lambda prompt="": next(replies))


def test_set_break_glass_password_creates_the_admin_with_an_audit_and_no_hash(seeded_template, tmp_path, fake_dir,
                                                                              monkeypatch):
    application = _ldap_app(seeded_template, tmp_path, fake_dir)
    try:
        assert _user(application, BREAK_GLASS) is None
        _prompts(monkeypatch, BG_PASSWORD, BG_PASSWORD)
        result = application.test_cli_runner().invoke(args=["set-break-glass-password"])
        assert result.exit_code == 0, result.output
        assert f"Created the break-glass account {BREAK_GLASS}: password set." in result.output
        assert BG_PASSWORD not in result.output
        user = _user(application, BREAK_GLASS)
        assert user.role_code == ROLE_SYS_ADMIN and user.active and user.display_name == "Emergency admin"
        rows = _audit_rows(application, user.id)
        assert [(r.action, r.reason) for r in rows] == [
            ("CREATE", "Emergency (break-glass) admin account, created from the server command line."),
            ("UPDATE", "Break-glass password set")]
        for row in rows:
            text = f"{row.before_json} {row.after_json}".lower()
            assert "password" not in text and "scrypt" not in text and "pbkdf2" not in text and user.password_hash not in text
        assert _sign_in(application, BREAK_GLASS, BG_PASSWORD).status_code == 200
        assert fake_dir.untouched
    finally:
        db.dispose()


def test_set_break_glass_password_again_changes_the_password_and_ends_its_sessions(ldap_app, monkeypatch):
    bg = Api(ldap_app, None)
    bg.login(BREAK_GLASS, BG_PASSWORD)
    new = "A-Brand-New-Sealed-Pass-2"
    _prompts(monkeypatch, new, new)
    result = ldap_app.test_cli_runner().invoke(args=["set-break-glass-password"])
    assert result.exit_code == 0 and f"Updated the break-glass account {BREAK_GLASS}" in result.output
    assert bg.get(f"{API}/session").status_code == 401  # signed in with the old password: signed out
    _login_failed(_sign_in(ldap_app, BREAK_GLASS, BG_PASSWORD))
    assert _sign_in(ldap_app, BREAK_GLASS, new).status_code == 200
    reasons = [r.reason for r in _audit_rows(ldap_app, _user(ldap_app, BREAK_GLASS).id)]
    assert reasons.count("Break-glass password set") == 2


@pytest.mark.parametrize("answers, message", [
    (("Fifteen-chars-1",), "at least 16 characters"),
    (("", ), "at least 16 characters"),
    (("Sixteen-chars-12", "Sixteen-chars-13"), "Passwords do not match."),
])
def test_set_break_glass_password_refuses_short_or_mistyped_passwords(ldap_app, monkeypatch, answers, message):
    before = _user(ldap_app, BREAK_GLASS).password_hash
    _prompts(monkeypatch, *answers)
    result = ldap_app.test_cli_runner().invoke(args=["set-break-glass-password"])
    assert result.exit_code != 0 and message in result.output
    assert _user(ldap_app, BREAK_GLASS).password_hash == before
    assert _sign_in(ldap_app, BREAK_GLASS, BG_PASSWORD).status_code == 200


def test_set_break_glass_password_needs_the_name_in_ldap_env(app, monkeypatch):
    _prompts(monkeypatch)  # must not even ask
    result = app.test_cli_runner().invoke(args=["set-break-glass-password"])
    assert result.exit_code != 0 and "BREAK_GLASS_USERNAME is not set" in result.output and "ldap.env" in result.output


def test_set_break_glass_password_works_in_local_mode_too(seeded_template, tmp_path, monkeypatch):
    application = _app_from(seeded_template, tmp_path, break_glass_username=BREAK_GLASS)
    try:
        _prompts(monkeypatch, BG_PASSWORD, BG_PASSWORD)
        result = application.test_cli_runner().invoke(args=["set-break-glass-password"])
        assert result.exit_code == 0 and "Created" in result.output and "AUTH_MODE is local" in result.output
        assert _sign_in(application, BREAK_GLASS, BG_PASSWORD).status_code == 200
    finally:
        db.dispose()


def test_set_break_glass_password_warns_when_the_account_is_not_an_active_admin(ldap_app, jane, monkeypatch):
    bg = _user(ldap_app, BREAK_GLASS)
    _ok(jane, "patch", f"{API}/users/{bg.id}", {"active": False, "reason": "Sealed again"})
    _prompts(monkeypatch, BG_PASSWORD, BG_PASSWORD)
    result = ldap_app.test_cli_runner().invoke(args=["set-break-glass-password"])
    assert result.exit_code == 0 and "Warning" in result.output and "not active" in result.output


# ---------------------------------------------------------------- Users & access in directory mode

def test_adding_a_person_needs_no_password_and_stores_the_windows_username(ldap_app, jane):
    created = _ok(jane, "post", f"{API}/users", {"username": "company\\u55555", "displayName": "Not In App",
                                                 "role": "EXECUTIVE"}, status=201)
    assert created["username"] == "U55555"
    user = _user(ldap_app, "U55555")
    assert user.password_hash.startswith(("scrypt:", "pbkdf2:"))  # a random, unusable hash
    rows = _audit_rows(ldap_app, user.id)
    assert [(r.action, r.reason) for r in rows] == [("CREATE", user_service.DIRECTORY_ACCOUNT_NOTE)]
    # Added: the directory password now lets them in, the MOCK password does not.
    _login_failed(_sign_in(ldap_app, "U55555", MOCK_PASSWORD))
    assert _sign_in(ldap_app, *NOT_IN_APP).status_code == 200


def test_adding_a_department_head_through_the_api_scopes_their_sign_in(ldap_app, jane):
    _ok(jane, "post", f"{API}/users", {"username": "U55555", "role": "DEPT_HEAD", "departmentIds": [str(G3)]},
        status=201)
    body = _sign_in(ldap_app, *NOT_IN_APP).get_json()
    assert body["user"]["role"] == "DEPT_HEAD" and body["user"]["departmentIds"] == ["3"]


@pytest.mark.parametrize("password", ["Some-Pass-123", "", MOCK_PASSWORD])
def test_a_password_is_refused_in_directory_mode(ldap_app, jane, password):
    res = jane.post(f"{API}/users", json={"username": "U55555", "role": "EXECUTIVE", "password": password})
    body = _err(res, 400, "VALIDATION_FAILED", "password")
    assert "Windows password" in body["fieldErrors"][0]["message"]
    assert _user(ldap_app, "U55555") is None


@pytest.mark.parametrize("username", ["jsmith", "X12345", "U12a", "U", "new.user", "U1*"])
def test_the_username_must_be_a_windows_username(ldap_app, jane, username):
    before = _count(ldap_app, AppUser)
    _err(jane.post(f"{API}/users", json={"username": username, "role": "EXECUTIVE"}), 400, "VALIDATION_FAILED",
         "username")
    assert _count(ldap_app, AppUser) == before


def test_the_windows_username_message_says_what_to_type(jane):
    body = _err(jane.post(f"{API}/users", json={"username": "jsmith", "role": "EXECUTIVE"}), 400, "VALIDATION_FAILED",
                "username")
    assert body["fieldErrors"][0]["message"] == "Enter the person's Windows username, for example U12345."


@pytest.mark.parametrize("username", [BREAK_GLASS, "CPC.BREAKGLASS"])
def test_the_break_glass_name_is_managed_on_the_server_only(ldap_app, jane, username):
    body = _err(jane.post(f"{API}/users", json={"username": username, "role": "SYS_ADMIN"}), 400, "VALIDATION_FAILED",
                "username")
    assert "set-break-glass-password" in body["fieldErrors"][0]["message"]


@pytest.mark.parametrize("spelling", ["u12345", "COMPANY\\U12345", "U12345@company.local"])
def test_the_same_person_in_another_spelling_is_a_duplicate(ldap_app, jane, spelling):
    _err(jane.post(f"{API}/users", json={"username": spelling, "role": "EXECUTIVE"}), 409, "DUPLICATE")


def test_local_mode_still_takes_passwords_and_any_username(admin):
    """The demo is unchanged: AUTH_MODE=local accepts a password and a non-Windows username."""
    created = _ok(admin, "post", f"{API}/users", {"username": "new.person", "role": "EXECUTIVE",
                                                  "password": "Pass-12345"}, status=201)
    assert created["username"] == "new.person"
    assert _sign_in(admin.app, "new.person", "Pass-12345").status_code == 200


# ---------------------------------------------------------------- GET /users/directory-lookup

LOOKUP = f"{API}/users/directory-lookup"


def test_lookup_fills_in_the_display_name(jane, fake_dir):
    assert _ok(jane, "get", f"{LOOKUP}?username=company%5Cu55555") == {
        "username": "U55555", "displayName": "Not In App", "alreadyAdded": False}
    assert fake_dir.binds == [SVC]  # looked up with the service account only
    assert _ok(jane, "get", f"{LOOKUP}?username=U22222") == {
        "username": "U22222", "displayName": "Ali Hassan", "alreadyAdded": True}


def test_lookup_of_someone_not_in_the_directory_is_404(jane):
    _err(jane.get(f"{LOOKUP}?username=U99999"), 404, "NOT_FOUND")
    _err(jane.get(f"{LOOKUP}?username=U66666"), 404, "NOT_FOUND")  # not unique


@pytest.mark.parametrize("query", ["", "?username=", "?username=jsmith", "?username=U1*", f"?username={BREAK_GLASS}"])
def test_lookup_needs_a_windows_username(jane, fake_dir, query):
    _err(jane.get(f"{LOOKUP}{query}"), 400, "VALIDATION_FAILED", "username")
    assert fake_dir.untouched


def test_lookup_refuses_unknown_parameters(jane):
    _err(jane.get(f"{LOOKUP}?username=U12345&filter=x"), 400, "VALIDATION_FAILED")


def test_lookup_while_the_directory_is_down_is_503(jane, fake_dir):
    fake_dir.down = True
    res = jane.get(f"{LOOKUP}?username=U12345")
    assert _err(res, 503, "DIRECTORY_UNAVAILABLE")["message"] == UNAVAILABLE


def test_lookup_in_local_mode_is_404(admin):
    _err(admin.get(f"{LOOKUP}?username=U12345"), 404, "NOT_FOUND")


@pytest.mark.parametrize("account", [CARL, TARA, ALI])
def test_lookup_is_for_admins_only(ldap_app, fake_dir, account):
    api = Api(ldap_app, None)
    api.login(*account)
    fake_dir.reset()
    _err(api.get(f"{LOOKUP}?username=U12345"), 403, "FORBIDDEN")
    assert fake_dir.untouched


def test_lookup_signed_out_is_401(ldap_app, fake_dir):
    _err(ldap_app.test_client().get(f"{LOOKUP}?username=U12345"), 401, "UNAUTHENTICATED")
    assert fake_dir.untouched


def test_the_break_glass_admin_can_look_people_up(ldap_app):
    bg = Api(ldap_app, None)
    bg.login(BREAK_GLASS, BG_PASSWORD)
    assert _ok(bg, "get", f"{LOOKUP}?username=U55555")["displayName"] == "Not In App"


# ---------------------------------------------------------------- GET /session/options (public)

def test_sign_in_options_in_directory_mode(ldap_app, fake_dir):
    res = ldap_app.test_client().get(f"{API}/session/options")
    assert res.status_code == 200
    assert res.get_json() == {"authMode": "ldap", "usernameHint": "Windows username, e.g. U12345",
                              "mockAccounts": False}
    text = res.get_data(as_text=True)
    for secret in (SVC_PASSWORD, SVC, "svc-cpc", BASE, "dc01", "company.local", BREAK_GLASS, "sAMAccountName"):
        assert secret not in text
    assert fake_dir.untouched


def test_sign_in_options_never_list_the_mock_accounts_in_directory_mode(seeded_template, tmp_path, fake_dir):
    application = _ldap_app(seeded_template, tmp_path, fake_dir, profile="demo", local_env=True)
    try:
        assert application.test_client().get(f"{API}/session/options").get_json()["mockAccounts"] is False
    finally:
        db.dispose()


def test_sign_in_options_in_local_mode(anon):
    assert _ok(anon, "get", f"{API}/session/options") == {"authMode": "local", "usernameHint": None,
                                                          "mockAccounts": False}  # the test profile is not a demo


def test_the_session_says_which_sign_in_is_used(admin, jane):
    assert _ok(admin, "get", f"{API}/session")["authMode"] == "local"
    assert _ok(jane, "get", f"{API}/session")["authMode"] == "ldap"


def test_no_session_answer_carries_directory_settings(ldap_app, jane):
    for res in (jane.get(f"{API}/session"), _sign_in(ldap_app, *JANE)):
        text = res.get_data(as_text=True)
        assert SVC_PASSWORD not in text and SVC not in text and "dc01" not in text and JANE[1] not in text


# ---------------------------------------------------------------- the seeder in directory mode

def test_an_empty_database_gets_only_the_roles_in_directory_mode(empty_template, tmp_path, fake_dir):
    """No demo data and no accounts at all: in particular no shared-password mock accounts."""
    from app.models import AppRole
    from app.seed.demo_seeder import seed_if_empty

    application = _ldap_app(empty_template, tmp_path, fake_dir)
    try:
        with application.app_context():
            assert seed_if_empty() == {"roles": 9}
        assert _count(application, AppUser) == 0
        assert _count(application, AppRole) == 9
        _login_failed(_sign_in(application, "mock.admin", MOCK_PASSWORD))
        assert fake_dir.untouched
    finally:
        db.dispose()


def test_an_existing_demo_database_keeps_working_and_gains_no_mock_accounts(ldap_app):
    from app.seed.demo_seeder import seed_if_empty

    before = _count(ldap_app, AppUser)
    with ldap_app.app_context():
        assert seed_if_empty() is None  # not empty: nothing is seeded
    assert _count(ldap_app, AppUser) == before
    _login_failed(_sign_in(ldap_app, "mock.admin", MOCK_PASSWORD))


# ---------------------------------------------------------------- flask create-user in directory mode

def test_create_user_asks_no_password_and_stores_the_windows_username(ldap_app, monkeypatch):
    _prompts(monkeypatch)  # any prompt would fail: none is expected
    result = ldap_app.test_cli_runner().invoke(
        args=["create-user", "--username", "company\\u55555", "--role", "DEPT_HEAD", "--department", "g1"])
    assert result.exit_code == 0, result.output
    assert "Created DEPT_HEAD user U55555" in result.output and "signs in with the Windows password" in result.output
    rows = _audit_rows(ldap_app, _user(ldap_app, "U55555").id)
    assert [r.reason for r in rows] == [user_service.DIRECTORY_ACCOUNT_NOTE]
    res = _sign_in(ldap_app, *NOT_IN_APP)
    assert res.status_code == 200 and res.get_json()["user"]["departmentIds"] == ["1"]


@pytest.mark.parametrize("username, message", [("jsmith", "Windows username"),
                                               (BREAK_GLASS, "set-break-glass-password")])
def test_create_user_refuses_non_windows_usernames(ldap_app, monkeypatch, username, message):
    _prompts(monkeypatch)
    result = ldap_app.test_cli_runner().invoke(args=["create-user", "--username", username, "--role", "EXECUTIVE"])
    assert result.exit_code != 0 and message in result.output and "Traceback" not in result.output


# ---------------------------------------------------------------- flask check-ldap

def _check_ldap(app, *args):
    return app.test_cli_runner().invoke(args=["check-ldap", *args])


def test_check_ldap_reports_every_step_and_never_shows_the_password(ldap_app):
    result = _check_ldap(ldap_app, "--username", "u12345")
    assert result.exit_code == 0, result.output
    out = result.output
    assert SVC_PASSWORD not in out and JANE[1] not in out
    assert "LDAP_BIND_PASSWORD:" in out and "(set, not shown)" in out
    assert "dc01.company.local" in out and BASE in out and "sAMAccountName" in out
    assert f"OK    Service account {SVC} signed in." in out
    assert f"OK    Search base {BASE} found." in out
    assert f"OK    User U12345 found: CN=Jane Smith,{BASE}, display name 'Jane Smith'." in out
    assert out.rstrip().endswith("All checks passed.")


def test_check_ldap_without_a_username_checks_the_connection_only(ldap_app):
    result = _check_ldap(ldap_app)
    assert result.exit_code == 0 and "User " not in result.output and "All checks passed." in result.output


def test_check_ldap_explains_a_wrong_service_password(ldap_app):
    ldap_app.config["SETTINGS"].ldap_bind_password = "wrong-service-password"
    result = _check_ldap(ldap_app)
    assert result.exit_code != 0 and "wrong-service-password" not in result.output
    assert f"FAIL  Service account {SVC}" in result.output
    assert f"What to check: {directory_module.HINT_SERVICE_ACCOUNT}" in result.output
    assert "The directory check failed" in result.output


def test_check_ldap_explains_an_unreachable_server(ldap_app, fake_dir):
    fake_dir.down = True
    result = _check_ldap(ldap_app)
    assert result.exit_code != 0 and "FAIL" in result.output
    assert f"What to check: {directory_module.HINT_NETWORK}" in result.output


def test_check_ldap_explains_a_wrong_base_dn(ldap_app):
    ldap_app.config["SETTINGS"].ldap_base_dn = "OU=Nobody,DC=company,DC=local"
    result = _check_ldap(ldap_app)
    assert result.exit_code != 0 and "FAIL  Search base OU=Nobody,DC=company,DC=local" in result.output
    assert f"What to check: {directory_module.HINT_BASE_DN}" in result.output


@pytest.mark.parametrize("username, expected", [
    ("U99999", "FAIL  User U99999 was not found under"),
    ("U66666", "FAIL  User U66666 was not found under"),     # not unique
    ("jsmith", "FAIL  JSMITH does not match LDAP_USERNAME_PATTERN"),
])
def test_check_ldap_reports_a_user_it_cannot_find(ldap_app, username, expected):
    result = _check_ldap(ldap_app, "--username", username)
    assert result.exit_code != 0 and expected in result.output


def test_check_ldap_in_local_mode_names_the_missing_setting(app, monkeypatch):
    for key in ("LDAP_SERVER", "LDAP_CA_FILE", "LDAP_BASE_DN", "LDAP_BIND_DN", "LDAP_BIND_PASSWORD"):
        monkeypatch.delenv(key, raising=False)
    result = _check_ldap(app)
    assert result.exit_code != 0
    assert "AUTH_MODE=ldap needs LDAP_SERVER (the directory server name). Set it in ldap.env" in result.output
    assert "Traceback" not in result.output


# ---------------------------------------------------------------- the directory module on its own

def test_directory_helpers_with_a_mock_connection(ldap_app, fake_dir):
    settings = ldap_app.config["SETTINGS"]
    directory = Directory(settings, fake_dir.factory)
    found = directory.lookup(" company\\u22222 ")
    assert (found.username, found.display_name, found.dn) == ("U22222", "Ali Hassan", f"CN=Ali Hassan,OU=Engineers,{BASE}")
    assert directory.lookup("U99999") is None and directory.lookup("nobody") is None
    assert directory.authenticate("U22222", ALI[1]) == found
    assert directory.authenticate("U22222", "wrong") is None
    assert directory.authenticate("U22222", "") is None and directory.authenticate("U22222", None) is None
    steps = directory.check("U22222")
    assert all(step.ok for step in steps) and len(steps) == 3


def test_a_factory_error_becomes_directory_unavailable(ldap_app):
    from app.exceptions import DirectoryUnavailable

    def broken(user, password):
        raise OSError("[Errno 11001] getaddrinfo failed")

    directory = Directory(ldap_app.config["SETTINGS"], broken)
    with pytest.raises(DirectoryUnavailable) as caught:
        directory.lookup("U12345")
    assert caught.value.hint == directory_module.HINT_DNS and caught.value.status == 503
    assert caught.value.message == UNAVAILABLE


@pytest.mark.parametrize("error, hint", [
    ("[Errno 11001] getaddrinfo failed", "HINT_DNS"),
    ("invalid server address", "HINT_DNS"),
    ("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed", "HINT_CERTIFICATE"),
    ("socket connection error while opening: timed out", "HINT_NETWORK"),
    ("[WinError 10061] No connection could be made", "HINT_NETWORK"),
])
def test_connection_errors_get_a_plain_words_hint(error, hint):
    assert directory_module.explain(OSError(error)) == getattr(directory_module, hint)


def test_any_tls_error_points_at_the_certificate():
    assert directory_module.explain(ssl.SSLError(1, "handshake failure")) == directory_module.HINT_CERTIFICATE
    mismatch = ssl.SSLCertVerificationError(1, "hostname mismatch")
    assert directory_module.explain(mismatch) == directory_module.HINT_CERTIFICATE
