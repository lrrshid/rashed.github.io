"""Settings > Database (ported from the Asset Availability project; owner choices, 24 Nov 2026: "exactly like the
reference" and a clean start).

The running database is shown read-only with its health and whether it holds the demo data; a candidate is tested with
read-only stages (connect, schema, permissions, data) and "staged for restart", which changes nothing in the running
app. The new database must start clean: a copy of the demo database (its mock.* accounts) is refused, an empty one
passes, the Oracle profile refuses to start on demo data, and `flask setup-database` makes the administrator and the
standard lists on an empty database. Candidates here are SQLite files in a temporary data folder
(database_provider.DATA_DIR is pointed at it); the Oracle candidate is checked for validation, the approved-destination
rule and secrecy, and the runtime grants file is checked to cover every table.
"""
from __future__ import annotations

import json
import shutil
import sqlite3

import pytest
from sqlalchemy import func, select

from app.core.config import ConfigError, sqlite_path
from app.extensions import db
from app.models import AppUser, Base, CapabilityCategory, Department
from app.security.mock_credentials import MOCK_PASSWORD
from app.seed.fixture_data import MOCK_USERS
from app.services.connections import database_provider
from tests.conftest import TEST_ACCOUNTS

# The test database's demo accounts: the demo's own (one per role of the structure) and the test-only ones.
DEMO_ACCOUNTS = len(MOCK_USERS) + len(TEST_ACCOUNTS)
from tests.conftest import Api

API = "/api/v1/connections"


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    folder = tmp_path / "data"
    folder.mkdir()
    monkeypatch.setattr(database_provider, "DATA_DIR", folder)
    return folder


@pytest.fixture
def adm(app) -> Api:
    api = Api(app, "mock.admin")
    res = api.post(f"{API}/reauth", json={"password": MOCK_PASSWORD})
    assert res.status_code == 200, res.get_json()
    return api


def _ok(api: Api, method: str, path: str, body=None, status=200):
    res = api.get(path) if method == "get" else getattr(api, method)(path, json=body)
    assert res.status_code == status, (res.status_code, res.get_json(silent=True))
    return res.get_json()


def _copy(app, target):
    """A copy of the running test database (sqlite3 backup)."""
    source = sqlite3.connect(sqlite_path(app.config["SETTINGS"]))
    copy = sqlite3.connect(target)
    with copy:
        source.backup(copy)
    copy.close()
    source.close()
    return target


def _sqlite_profile(api: Api, file_name: str, name="Candidate") -> dict:
    profile = _ok(api, "post", f"{API}/profiles", {"kind": "DATABASE", "provider": "sqlite", "name": name,
                                                   "purpose": "PRIMARY"}, status=201)
    return _ok(api, "put", f"{API}/profiles/{profile['id']}/draft",
               {"draftVersion": profile["draft"]["version"], "fields": {"fileName": file_name}})


def _test(api: Api, profile: dict) -> dict:
    return _ok(api, "post", f"{API}/profiles/{profile['id']}/test", {})


def _outcomes(result: dict) -> dict:
    return {r["stage"]: (r["outcome"], r["code"]) for r in result["results"]}


def _stage(api: Api, profile_id: str):
    current = _ok(api, "get", f"{API}/profiles/{profile_id}")
    return api.post(f"{API}/profiles/{profile_id}/apply",
                    json={"draftVersion": current["draft"]["version"], "version": current["version"]})


def test_the_running_database_is_shown_read_only_with_its_demo_data(adm):
    status = _ok(adm, "get", f"{API}/database")
    running = status["running"]
    assert running["engine"] == "sqlite" and running["source"] == "ENV" and running["health"] == "HEALTHY"
    assert running["schemaVersion"] == running["expectedVersion"] == database_provider.expected_version("sqlite")
    assert running["demoAccounts"] == DEMO_ACCOUNTS  # the demo world: mock.admin, mock.commander, ...
    assert set(status["providers"]) == {"oracle", "sqlite"} and status["staged"] == []


def test_a_copy_of_the_demo_database_is_refused(adm, app, data_dir):
    _copy(app, data_dir / "demo-copy.db")
    profile = _sqlite_profile(adm, "demo-copy.db")
    result = _test(adm, profile)
    stages = _outcomes(result)
    assert stages["CONNECT"][0] == stages["SCHEMA"][0] == stages["PERMISSIONS"][0] == "PASSED"
    assert stages["DATA"] == ("FAILED", "DEMO_DATA")
    assert f"{DEMO_ACCOUNTS} demo account(s)" in result["results"][3]["message"]
    res = _stage(adm, profile["id"])
    assert res.status_code == 409 and res.get_json()["code"] == "NOT_READY_NOT_TESTED"


def test_an_empty_database_passes_and_is_staged_for_the_restart(adm, empty_template, data_dir):
    shutil.copyfile(empty_template, data_dir / "clean.db")
    profile = _sqlite_profile(adm, "clean.db")
    result = _test(adm, profile)
    assert _outcomes(result) == {"CONNECT": ("PASSED", None), "SCHEMA": ("PASSED", None),
                                 "PERMISSIONS": ("PASSED", None), "DATA": ("PASSED", "EMPTY")}
    assert "setup-database" in result["results"][3]["message"]
    staged = _stage(adm, profile["id"])
    assert staged.status_code == 200, staged.get_json()
    body = staged.get_json()
    assert body["state"] == "STAGED" and body["enabled"] is False
    assert body["cutover"]["envLines"] == ["APP_PROFILE=demo", "DEMO_DB_PATH=data/clean.db"]
    assert "setup-database" in body["cutover"]["setupCommand"]
    # Staging changed nothing in the running app.
    running = _ok(adm, "get", f"{API}/database")["running"]
    assert running["demoAccounts"] == DEMO_ACCOUNTS and running["matchesProfile"] is None


def test_a_missing_or_foreign_file_fails_at_its_stage(adm, data_dir):
    missing = _test(adm, _sqlite_profile(adm, "nowhere.db", "Missing"))
    assert _outcomes(missing)["CONNECT"] == ("FAILED", "NOT_FOUND") and _outcomes(missing)["DATA"][0] == "SKIPPED"
    sqlite3.connect(data_dir / "other.db").execute("CREATE TABLE something (id INTEGER)").connection.close()
    foreign = _test(adm, _sqlite_profile(adm, "other.db", "Foreign"))
    assert _outcomes(foreign)["SCHEMA"] == ("FAILED", "NO_SCHEMA")


def test_an_oracle_candidate_is_validated_kept_secret_and_needs_an_approved_destination(adm, app):
    app.config["EGRESS_RESOLVER"] = lambda host, port: ["10.1.2.3"]
    profile = _ok(adm, "post", f"{API}/profiles", {"kind": "DATABASE", "provider": "oracle", "name": "Production",
                                                   "purpose": "PRIMARY"}, status=201)
    bad = adm.put(f"{API}/profiles/{profile['id']}/draft", json={
        "draftVersion": profile["draft"]["version"], "fields": {"host": "db01:1521", "username": "1BAD"}})
    assert bad.status_code == 400
    saved = _ok(adm, "put", f"{API}/profiles/{profile['id']}/draft", {
        "draftVersion": profile["draft"]["version"],
        "fields": {"host": "db01.company.local", "serviceName": "CPCPDB", "username": "cpc_app", "schema": "cpc_owner"},
        "secrets": {"password": {"action": "replace", "value": "Oracle-Secret-9"}}})
    assert saved["draft"]["fields"]["username"] == "CPC_APP" and "Oracle-Secret-9" not in json.dumps(saved)
    result = _test(adm, saved)
    assert _outcomes(result)["CONNECT"] == ("FAILED", "NOT_APPROVED")  # nothing is reached before it is approved


def test_the_runtime_grants_cover_every_table_the_app_maps():
    grants = database_provider.required_grants()
    missing = [t for t in sorted(Base.metadata.tables) if t.upper() not in grants]
    assert not missing, f"db/oracle/runtime-grants.sql has no grant for {missing}"
    assert {"SELECT", "INSERT"} <= grants["SETTING_TEST"] and "DELETE" not in grants["AUDIT_EVENT"]


def test_the_oracle_start_up_guard_refuses_a_database_holding_the_demo_data(app):
    from app import refuse_demo_data
    with app.app_context():
        with pytest.raises(ConfigError, match="demo data"):
            refuse_demo_data(db.engine)


def test_the_oracle_start_up_guard_accepts_an_empty_database(empty_app):
    from app import refuse_demo_data
    with empty_app.app_context():
        refuse_demo_data(db.engine)


def test_mock_accounts_are_reserved_for_the_local_demo(seeded_template, tmp_path):
    from tests.conftest import _app_from
    server = _app_from(seeded_template, tmp_path, local_env=False)
    admin = Api(server, "mock.admin")
    res = admin.post("/api/v1/users", json={"username": "mock.extra", "displayName": "Extra", "role": "VIEWER",
                                            "password": "Long-Password-1"})
    assert res.status_code == 400 and res.get_json()["fieldErrors"][0]["field"] == "username"


def test_setup_database_makes_the_administrator_and_the_standard_lists_on_an_empty_database(empty_app, monkeypatch):
    monkeypatch.setattr("getpass.getpass", lambda prompt="": "It-Admin-Pass-1")
    runner = empty_app.test_cli_runner()
    refused = runner.invoke(args=["setup-database", "--admin", "mock.admin"])
    assert refused.exit_code != 0 and "reserved for the demo" in refused.output
    done = runner.invoke(args=["setup-database", "--admin", "it.admin", "--display-name", "IT Administrator"])
    assert done.exit_code == 0, done.output
    with empty_app.app_context():
        users = db.session().scalars(select(AppUser)).all()
        assert [(u.username, u.role_code) for u in users] == [("it.admin", "SYS_ADMIN")]
        assert db.session().scalar(select(func.count()).select_from(Department)) > 0
        assert db.session().scalar(select(func.count()).select_from(CapabilityCategory)) > 0
    again = runner.invoke(args=["setup-database", "--admin", "other.admin"])
    assert again.exit_code != 0 and "already has accounts" in again.output
    signed_in = empty_app.test_client().post("/api/v1/session", json={"username": "it.admin",
                                                                      "password": "It-Admin-Pass-1"})
    assert signed_in.status_code == 200


def test_setup_database_can_read_the_password_from_standard_input(empty_app, monkeypatch):
    """The VM installer (deployment/install.sh) pipes the password in: never a prompt, never a command-line argument."""
    monkeypatch.setattr("getpass.getpass", lambda prompt="": pytest.fail("no prompt with --password-stdin"))
    runner = empty_app.test_cli_runner()
    empty = runner.invoke(args=["setup-database", "--admin", "it.first", "--password-stdin"], input="\n")
    assert empty.exit_code != 0 and "No password" in empty.output
    done = runner.invoke(args=["setup-database", "--admin", "it.first", "--password-stdin"], input="Piped-Pass-123\n")
    assert done.exit_code == 0, done.output
    assert "Piped-Pass-123" not in done.output
    signed_in = empty_app.test_client().post("/api/v1/session", json={"username": "it.first", "password": "Piped-Pass-123"})
    assert signed_in.status_code == 200
