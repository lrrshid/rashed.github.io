"""Settings > connections (ported from the Asset Availability project): the company directory managed from the website.

Offline: ldap3's MOCK_SYNC directory of test_ldap.py stands in for Active Directory (DIRECTORY_CONNECTION_FACTORY),
and app.config["EGRESS_RESOLVER"] answers DNS. Covers who may use it (system administrators only, never in a role
preview), typing the password again, certificates, approved destinations, drafts and secrets (keep, replace, clear;
never returned, never audited), the staged tests, apply and staleness, the sign-in method switch and its lockout guard,
the ldap.env import, rollback, history and the server's recovery commands.
"""
from __future__ import annotations

import datetime as dt
import io
import json

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from sqlalchemy import select

from app.core.database import write_intent
from app.extensions import db
from app.models import AuditEvent, SettingRevision
from app.security.mock_credentials import MOCK_PASSWORD
from app.services import user_service
from app.services.connections.config_service import effective
from tests.conftest import REFERENCE_NOW, Api, _app_from
from tests.integration.test_ldap import BASE, JANE, SVC, SVC_PASSWORD, TARA, FakeDirectory

API = "/api/v1/connections"
HOST = "dc01.company.local"


def make_cert(ca: bool = True, days: int = 365) -> tuple[bytes, bytes]:
    """(certificate PEM, private key PEM) of a fresh self-signed certificate."""
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Company Root CA")])
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(REFERENCE_NOW - dt.timedelta(days=1))
            .not_valid_after(REFERENCE_NOW + dt.timedelta(days=days))
            .add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True)
            .sign(key, hashes.SHA256()))
    key_pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption())
    return cert.public_bytes(serialization.Encoding.PEM), key_pem


def _ok(api: Api, method: str, path: str, json_body=None, status=200):
    res = api.get(path) if method == "get" else getattr(api, method)(path, json=json_body)
    assert res.status_code == status, (res.status_code, res.get_json(silent=True))
    return res.get_json()


def _delete(api: Api, path: str, body: dict):
    return api.client.delete(path, json=body, headers={"X-CSRF-Token": api.csrf})


def _err(res, status, code=None):
    assert res.status_code == status, (res.status_code, res.get_json())
    if code:
        assert res.get_json()["code"] == code, res.get_json()
    return res.get_json()


@pytest.fixture
def fake():
    return FakeDirectory()


@pytest.fixture
def setup_app(app, fake):
    app.config["DIRECTORY_CONNECTION_FACTORY"] = fake.factory
    app.config["EGRESS_RESOLVER"] = lambda host, port: ["10.1.2.3"]
    with app.test_request_context("/"), write_intent():
        actor = user_service.find("mock.admin")
        user_service.create_user(user_service.directory_username(JANE[0]), "Jane Smith", "SYS_ADMIN", None,
                                 actor=actor, note=user_service.DIRECTORY_ACCOUNT_NOTE)
        user_service.create_user(user_service.directory_username(TARA[0]), "Tara Top", "VIEWER", None,
                                 actor=actor, note=user_service.DIRECTORY_ACCOUNT_NOTE)
    return app


@pytest.fixture
def adm(setup_app) -> Api:
    api = Api(setup_app, "mock.admin")
    _ok(api, "post", f"{API}/reauth", {"password": MOCK_PASSWORD})
    return api


def _cert(api: Api, pem: bytes | None = None, name="Company Root CA"):
    pem = pem or make_cert()[0]
    return api.client.post(f"{API}/certificates", data={"name": name, "file": (io.BytesIO(pem), "ca.pem")},
                           headers={"X-CSRF-Token": api.csrf}, content_type="multipart/form-data")


def _ready_profile(api: Api, password=SVC_PASSWORD) -> dict:
    cert = _cert(api).get_json()
    _ok(api, "post", f"{API}/destinations", {"host": HOST, "port": 636, "purpose": "LDAP"}, status=201)
    profile = _ok(api, "post", f"{API}/profiles", {"kind": "LDAP", "provider": "ldap", "name": "Directory",
                                                   "purpose": "SIGN_IN"}, status=201)
    return _ok(api, "put", f"{API}/profiles/{profile['id']}/draft", {
        "draftVersion": profile["draft"]["version"],
        "fields": {"servers": [HOST], "caCertIds": [cert["id"]], "baseDn": BASE, "bindDn": SVC},
        "secrets": {"bindPassword": {"action": "replace", "value": password}}})


def _test(api: Api, profile: dict, **body) -> dict:
    return _ok(api, "post", f"{API}/profiles/{profile['id']}/test", body)


def _apply(api: Api, profile_id: str):
    current = _ok(api, "get", f"{API}/profiles/{profile_id}")
    return api.post(f"{API}/profiles/{profile_id}/apply",
                    json={"draftVersion": current["draft"]["version"], "version": current["version"]})


def _outcomes(result: dict) -> dict:
    return {r["stage"]: r["outcome"] for r in result["results"]}


# ---------------------------------------------------------------- who may use it

def test_only_a_system_administrator_may_open_the_connections(setup_app):
    for username in ("mock.exec", "mock.capability", "mock.viewer", "mock.head"):
        other = Api(setup_app, username)
        for method, path in (("get", "/overview"), ("get", "/profiles"), ("post", "/reauth"), ("put", "/sign-in"),
                             ("post", "/destinations"), ("get", "/database"), ("get", "/history")):
            res = other.get(f"{API}{path}") if method == "get" else getattr(other, method)(f"{API}{path}", json={})
            _err(res, 403, "FORBIDDEN")
    assert setup_app.test_client().get(f"{API}/overview").status_code == 401
    admin = Api(setup_app, "mock.admin")
    _err(admin.get(f"{API}/overview", headers={"X-View-As": "EXECUTIVE"}), 403)  # never in a role preview
    assert admin.get(f"{API}/overview").status_code == 200


def test_sensitive_steps_need_the_password_again(setup_app):
    api = Api(setup_app, "mock.admin")
    _err(api.post(f"{API}/destinations", json={"host": HOST, "port": 636, "purpose": "LDAP"}), 403, "REAUTH_REQUIRED")
    _err(api.post(f"{API}/reauth", json={"password": "wrong-password"}), 400, "VALIDATION_FAILED")
    assert api.get("/api/v1/session").status_code == 200  # a wrong password does not end the session
    _ok(api, "post", f"{API}/reauth", {"password": MOCK_PASSWORD})
    _ok(api, "post", f"{API}/destinations", {"host": HOST, "port": 636, "purpose": "LDAP"}, status=201)


def test_a_write_without_the_csrf_token_is_refused(adm):
    res = adm.client.post(f"{API}/destinations", json={"host": HOST, "port": 636, "purpose": "LDAP"})
    assert res.status_code == 403


# ---------------------------------------------------------------- certificates and destinations

def test_certificates_are_validated_and_never_include_a_private_key(adm):
    pem, key_pem = make_cert()
    _err(_cert(adm, pem + key_pem), 400, "VALIDATION_FAILED")
    _err(_cert(adm, b"not a certificate"), 400, "VALIDATION_FAILED")
    saved = _cert(adm, pem)
    assert saved.status_code == 201 and saved.get_json()["state"] == "VALID" and saved.get_json()["warning"] is None
    _err(_cert(adm, pem), 409, "DUPLICATE")
    leaf = _cert(adm, make_cert(ca=False)[0], name="A server certificate").get_json()
    assert "not marked as a CA" in leaf["warning"]
    listed = _ok(adm, "get", f"{API}/certificates")["items"]
    assert {c["name"] for c in listed} == {"Company Root CA", "A server certificate"}
    assert all("pem" not in c for c in listed)


@pytest.mark.parametrize("host", ["169.254.169.254", "http://dc01", "dc01:636", "*.local", "a b", "fe80::1"])
def test_destinations_refuse_unsafe_hosts(adm, host):
    _err(adm.post(f"{API}/destinations", json={"host": host, "port": 636, "purpose": "LDAP"}), 400)


def test_destinations_are_listed_and_unique(adm):
    rule = _ok(adm, "post", f"{API}/destinations", {"host": "DC01.Company.Local", "port": 636, "purpose": "LDAP"},
               status=201)
    assert rule["host"] == "dc01.company.local"
    _err(adm.post(f"{API}/destinations", json={"host": HOST, "port": 636, "purpose": "LDAP"}), 409, "DUPLICATE")
    _ok(adm, "post", f"{API}/destinations", {"host": "db01.company.local", "port": 1521, "purpose": "DATABASE"},
        status=201)
    assert [r["purpose"] for r in _ok(adm, "get", f"{API}/destinations")["items"]] == ["DATABASE", "LDAP"]
    _ok(adm, "patch", f"{API}/destinations/{rule['id']}", {"version": rule["version"], "port": 389})
    assert _delete(adm, f"{API}/destinations/{rule['id']}", {"version": rule["version"] + 1}).status_code == 204


# ---------------------------------------------------------------- drafts and secrets

def test_secrets_are_kept_replaced_and_cleared_but_never_returned(adm, setup_app):
    profile = _ready_profile(adm)
    text = json.dumps(profile)
    assert SVC_PASSWORD not in text and profile["draft"]["secrets"]["bindPassword"]["configured"] is True
    # keep (left out) and an unrelated edit
    profile = _ok(adm, "put", f"{API}/profiles/{profile['id']}/draft", {
        "draftVersion": profile["draft"]["version"], "fields": {**profile["draft"]["fields"], "port": 636}})
    assert profile["draft"]["secrets"]["bindPassword"]["configured"] is True
    # a placeholder never overwrites the secret
    _err(adm.put(f"{API}/profiles/{profile['id']}/draft", json={
        "draftVersion": profile["draft"]["version"], "fields": profile["draft"]["fields"],
        "secrets": {"bindPassword": {"action": "replace", "value": "********"}}}), 400)
    profile = _ok(adm, "put", f"{API}/profiles/{profile['id']}/draft", {
        "draftVersion": profile["draft"]["version"], "fields": profile["draft"]["fields"],
        "secrets": {"bindPassword": {"action": "clear"}}})
    assert profile["draft"]["secrets"]["bindPassword"]["configured"] is False
    assert profile["draft"]["blockers"][0] == "SECRET_MISSING"
    with setup_app.app_context():
        rows = db.session().scalars(select(AuditEvent).where(AuditEvent.entity_type == "SETTING_REVISION")).all()
        revisions = db.session().scalars(select(SettingRevision)).all()
        assert rows and all(SVC_PASSWORD not in (r.after_json or "") + (r.before_json or "") for r in rows)
        assert all("secrets_json" not in (r.after_json or "") for r in rows)
        assert any("bindPassword" in (r.after_json or "") for r in rows)  # which secret, never its value
        assert all(SVC_PASSWORD not in (r.secrets_json or "") for r in revisions)  # encrypted at rest


def test_a_draft_is_checked_and_protected_from_concurrent_edits(adm):
    profile = _ok(adm, "post", f"{API}/profiles", {"kind": "LDAP", "provider": "ldap", "name": "Directory",
                                                   "purpose": "SIGN_IN"}, status=201)
    _err(adm.put(f"{API}/profiles/{profile['id']}/draft", json={
        "draftVersion": profile["draft"]["version"], "fields": {"servers": ["ldaps://dc01"], "unknown": 1}}), 400)
    saved = _ok(adm, "put", f"{API}/profiles/{profile['id']}/draft", {
        "draftVersion": profile["draft"]["version"], "fields": {"servers": [HOST]}})
    _err(adm.put(f"{API}/profiles/{profile['id']}/draft", json={
        "draftVersion": profile["draft"]["version"], "fields": {"servers": [HOST]}}), 409, "STALE_VERSION")
    assert saved["state"] == "DRAFT" and "INVALID" in saved["draft"]["blockers"]


# ---------------------------------------------------------------- tests, apply and the sign-in method

def test_the_stages_pass_against_the_directory(adm, fake):
    profile = _ready_profile(adm)
    result = _test(adm, profile, sample={"username": "u12345", "password": JANE[1]})
    assert _outcomes(result) == {"NETWORK_TLS": "PASSED", "SERVICE_BIND": "PASSED", "SEARCH_BASE": "PASSED",
                                 "SAMPLE_LOOKUP": "PASSED", "SIGN_IN": "PASSED"}
    assert "Jane Smith" in result["results"][3]["message"]
    assert result["profile"]["draft"]["blockers"] == []
    assert JANE[1] not in json.dumps(result)


def test_a_wrong_service_password_fails_its_stage(adm):
    profile = _ready_profile(adm, password="Not-The-Password-1")
    result = _test(adm, profile)
    assert _outcomes(result)["SERVICE_BIND"] == "FAILED" and _outcomes(result)["SEARCH_BASE"] == "SKIPPED"
    _err(_apply(adm, profile["id"]), 409, "NOT_READY_NOT_TESTED")


def test_a_test_only_reaches_approved_destinations(adm, fake):
    profile = _ready_profile(adm)
    rule = _ok(adm, "get", f"{API}/destinations")["items"][0]
    assert _delete(adm, f"{API}/destinations/{rule['id']}", {"version": rule["version"]}).status_code == 204
    result = _test(adm, profile)
    assert _outcomes(result)["NETWORK_TLS"] == "FAILED" and result["results"][0]["code"] == "NOT_APPROVED"
    assert fake.untouched  # nothing was connected


def test_apply_needs_a_passed_test_of_this_exact_draft(adm, setup_app):
    profile = _ready_profile(adm)
    _err(_apply(adm, profile["id"]), 409, "NOT_READY_NOT_TESTED")
    _test(adm, profile)
    applied = _apply(adm, profile["id"])
    assert applied.status_code == 200, applied.get_json()
    active = applied.get_json()
    assert active["state"] == "ACTIVE" and active["enabled"] and active["activeRevisionNo"] == 1
    with setup_app.app_context():
        live = effective()
        assert live.ldap_servers == (HOST,) and live.ldap_bind_password == SVC_PASSWORD and live.auth_mode == "local"
    # an edit makes a new draft that needs its own test
    edited = _ok(adm, "put", f"{API}/profiles/{profile['id']}/draft", {"fields": {**active["active"]["fields"],
                                                                                 "timeoutSeconds": 7}})
    assert edited["draft"]["revisionNo"] == 2 and "NOT_TESTED" in edited["draft"]["blockers"]
    _err(_apply(adm, profile["id"]), 409, "NOT_READY_NOT_TESTED")


def test_the_directory_becomes_the_sign_in_method_only_after_an_admin_test_sign_in(adm, setup_app):
    profile = _ready_profile(adm)
    _test(adm, profile, sample={"username": TARA[0], "password": TARA[1]})  # a viewer, not an administrator
    assert _apply(adm, profile["id"]).status_code == 200
    _err(adm.put(f"{API}/sign-in", json={"method": "ldap"}), 409, "NEEDS_SIGN_IN_TEST")
    _test(adm, {"id": profile["id"]}, target="active", sample={"username": JANE[0], "password": JANE[1]})
    status = _ok(adm, "put", f"{API}/sign-in", {"method": "ldap"})
    assert status["method"] == "ldap" and status["source"] == "SETTINGS"
    # Sign-in now goes to the directory: Jane gets in with her Windows password, the demo password no longer works.
    jane = setup_app.test_client().post("/api/v1/session", json={"username": "u12345", "password": JANE[1]})
    assert jane.status_code == 200 and jane.get_json()["authMode"] == "ldap"
    mock = setup_app.test_client().post("/api/v1/session", json={"username": "mock.viewer", "password": MOCK_PASSWORD})
    assert mock.status_code == 401
    # The connection in use for sign-in cannot be switched off or deleted.
    current = _ok(adm, "get", f"{API}/profiles/{profile['id']}")
    _err(adm.post(f"{API}/profiles/{profile['id']}/disable", json={"version": current["version"]}), 409, "IN_USE")
    _ok(adm, "put", f"{API}/sign-in", {"method": "local", "version": status["version"]})


def test_outside_a_laptop_the_switch_needs_the_break_glass_admin(fake, seeded_template, tmp_path):
    application = _app_from(seeded_template, tmp_path, local_env=False, cookie_secure=False)
    application.config.update(DIRECTORY_CONNECTION_FACTORY=fake.factory,
                              EGRESS_RESOLVER=lambda host, port: ["10.1.2.3"])
    with application.test_request_context("/"), write_intent():
        user_service.create_user(user_service.directory_username(JANE[0]), "Jane Smith", "SYS_ADMIN", None,
                                 actor=user_service.find("mock.admin"), note=user_service.DIRECTORY_ACCOUNT_NOTE)
    api = Api(application, "mock.admin")
    _ok(api, "post", f"{API}/reauth", {"password": MOCK_PASSWORD})
    profile = _ready_profile(api)
    _test(api, profile, sample={"username": JANE[0], "password": JANE[1]})
    assert _apply(api, profile["id"]).status_code == 200
    _err(api.put(f"{API}/sign-in", json={"method": "ldap"}), 409, "NO_BREAK_GLASS")


def test_ldap_env_is_imported_as_a_draft_and_never_comes_back(fake, seeded_template, tmp_path):
    from tests.integration.test_ldap import LDAP
    pem = make_cert()[0]
    application = _app_from(seeded_template, tmp_path, **{**LDAP, "auth_mode": "local", "ldap_ca_data": pem.decode()})
    application.config.update(DIRECTORY_CONNECTION_FACTORY=fake.factory,
                              EGRESS_RESOLVER=lambda host, port: ["10.1.2.3"])
    api = Api(application, "mock.admin")
    _ok(api, "post", f"{API}/reauth", {"password": MOCK_PASSWORD})
    first = _ok(api, "post", f"{API}/import-env")
    assert first["created"] and first["profile"]["state"] == "DRAFT"
    assert first["profile"]["draft"]["secrets"]["bindPassword"]["configured"]
    assert _ok(api, "post", f"{API}/import-env")["created"] is False
    assert [r["host"] for r in _ok(api, "get", f"{API}/destinations")["items"]] == [HOST]
    assert len(_ok(api, "get", f"{API}/certificates")["items"]) == 1
    profile = first["profile"]
    _test(api, profile)
    assert _apply(api, profile["id"]).status_code == 200
    current = _ok(api, "get", f"{API}/profiles/{profile['id']}")
    _ok(api, "post", f"{API}/profiles/{profile['id']}/disable", {"version": current["version"]})
    with application.app_context():
        assert effective().ldap_servers == ()  # switched off in Settings: ldap.env's directory does not come back
    assert _ok(api, "get", f"{API}/overview")["config"]["sources"]["directory"] == "SETTINGS"


def test_rollback_makes_a_draft_that_needs_its_own_test(adm):
    profile = _ready_profile(adm)
    _test(adm, profile)
    first = _apply(adm, profile["id"]).get_json()
    _ok(adm, "put", f"{API}/profiles/{profile['id']}/draft", {"fields": {**first["active"]["fields"],
                                                                         "timeoutSeconds": 9}})
    second = _ok(adm, "get", f"{API}/profiles/{profile['id']}")
    _test(adm, second)
    second = _apply(adm, profile["id"]).get_json()
    old = next(r for r in second["revisions"] if r["revisionNo"] == 1)
    copied = _ok(adm, "post", f"{API}/profiles/{profile['id']}/rollback", {"revisionId": old["id"],
                                                                           "version": second["version"]})
    assert copied["draft"]["revisionNo"] == 3 and copied["draft"]["fields"]["timeoutSeconds"] == 5
    assert "NOT_TESTED" in copied["draft"]["blockers"]


def test_overview_history_and_diagnostics(adm):
    profile = _ready_profile(adm)
    overview = _ok(adm, "get", f"{API}/overview")
    assert overview["settingsKey"]["configured"] and overview["connections"]["LDAP"][0]["state"] == "DRAFT"
    assert overview["pendingDrafts"] and overview["signIn"]["method"] == "local"
    history = _ok(adm, "get", f"{API}/history?size=50")
    assert {e["entityType"] for e in history["items"]} >= {"SETTING_PROFILE", "SETTING_REVISION", "SETTING_CERT",
                                                           "EGRESS_RULE"}
    assert SVC_PASSWORD not in json.dumps(history)
    diag = _ok(adm, "get", f"{API}/diagnostics")
    assert diag["settingsKey"]["configured"] and diag["profile"] == "test"
    assert any(b["name"].startswith("SETTINGS_KEY") for b in diag["bootstrap"])
    assert profile["id"]


def test_recovery_from_the_command_line(adm, setup_app):
    profile = _ready_profile(adm)
    _test(adm, profile, sample={"username": JANE[0], "password": JANE[1]})
    _apply(adm, profile["id"])
    _ok(adm, "put", f"{API}/sign-in", {"method": "ldap"})
    runner = setup_app.test_cli_runner()
    refused = runner.invoke(args=["settings-recover", "--as", "mock.viewer", "--sign-in", "local"])
    assert refused.exit_code != 0 and "not an active system administrator" in refused.output
    done = runner.invoke(args=["settings-recover", "--as", "mock.admin", "--sign-in", "local", "--disable",
                               profile["id"]])
    assert done.exit_code == 0, done.output
    with setup_app.app_context():
        from app.services.connections import config_service
        live = config_service.refresh()
        assert live.auth_mode == "local" and live.ldap_servers == ()
    assert setup_app.test_client().post("/api/v1/session", json={"username": "mock.viewer",
                                                                 "password": MOCK_PASSWORD}).status_code == 200


def test_key_rotation_re_encrypts_every_secret(fake, seeded_template, tmp_path, monkeypatch):
    from app.core import secretbox
    old, new = secretbox.parse_key(secretbox.new_key_text()), secretbox.parse_key(secretbox.new_key_text())
    application = _app_from(seeded_template, tmp_path, settings_keys=(old,))
    application.config.update(DIRECTORY_CONNECTION_FACTORY=fake.factory,
                              EGRESS_RESOLVER=lambda host, port: ["10.1.2.3"])
    api = Api(application, "mock.admin")
    _ok(api, "post", f"{API}/reauth", {"password": MOCK_PASSWORD})
    profile = _ready_profile(api)
    application.config["SETTINGS"].settings_keys = (new, old)  # SETTINGS_KEY=new, SETTINGS_KEY_PREVIOUS=old
    result = application.test_cli_runner().invoke(args=["settings-rotate-key", "--as", "mock.admin"])
    assert result.exit_code == 0 and "1 revision(s)" in result.output, result.output
    application.config["SETTINGS"].settings_keys = (new,)  # the old key removed: the secret still reads
    tested = _test(api, profile)
    assert _outcomes(tested)["SERVICE_BIND"] == "PASSED"


def test_plain_ldap_is_an_explicit_choice_that_stays_flagged(adm):
    profile = _ready_profile(adm)
    plain = _ok(adm, "put", f"{API}/profiles/{profile['id']}/draft", {
        "draftVersion": profile["draft"]["version"],
        "fields": {**profile["draft"]["fields"], "security": "ldap", "port": 389, "caCertIds": []}})
    _ok(adm, "post", f"{API}/destinations", {"host": HOST, "port": 389, "purpose": "LDAP"}, status=201)
    result = _test(adm, plain)
    assert result["results"][0]["outcome"] == "WARNING" and result["results"][0]["code"] == "PLAINTEXT"
    assert result["profile"]["draft"]["health"] == "DEGRADED"


def test_the_heartbeat_never_waits_for_this_contexts_own_write_lock(app, monkeypatch):
    """A read request that writes (write_intent) may hold SQLite's write lock: the diagnostics heartbeat, written on its
    own connection, must not run then (it once waited out the 5 s busy timeout); on a plain read it still runs."""
    import time

    from app.services.connections import config_service
    calls = []
    monkeypatch.setattr(config_service, "_heartbeat", lambda state, generation: calls.append(generation))
    with app.test_request_context("/"), write_intent():
        user_service.find("mock.admin")  # this context's session now holds the write lock (BEGIN IMMEDIATE)
        started = time.monotonic()
        config_service.refresh()
        assert time.monotonic() - started < 2 and calls == []
    with app.test_request_context("/"):
        config_service.refresh()
        assert len(calls) == 1
