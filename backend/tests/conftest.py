"""Shared fixtures. Every test gets its own copy of a seeded SQLite file and a fixed clock, so the demo figures
(66 assets, 12 capabilities, 3 critical gaps, 13 active projects, 7 delayed) are repeatable on any day."""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import app.core.config as config_module
from app import create_app
from app.core.clock import FixedClock
from app.core.config import load_settings
from app.extensions import db
from app.security.mock_credentials import MOCK_PASSWORD

# Tests never read the machine's ldap.env: the suite runs with AUTH_MODE=local wherever it runs.
config_module.LDAP_ENV_FILE = Path(__file__).resolve().parent / "fixtures" / "ldap.env.absent"

ZONE = ZoneInfo("Asia/Dubai")
REFERENCE_NOW = datetime(2026, 10, 8, 10, 0, tzinfo=ZONE)  # reference day D = 2026-10-08


def make_settings(db_file: Path, **overrides):
    base = {
        "database_url": f"sqlite:///{db_file.as_posix()}",
        "timezone": "Asia/Dubai",
        "cookie_secure": False,
        "log_level": "WARNING",
        "local_env": True,
        "auth_mode": "local",
    }
    base.update(overrides)
    return load_settings("test", base)


@pytest.fixture(scope="session")
def seeded_template(tmp_path_factory) -> Path:
    from app.seed.demo_seeder import seed_demo

    path = tmp_path_factory.mktemp("template") / "seeded.db"
    app = create_app(make_settings(path), FixedClock(REFERENCE_NOW))
    with app.test_request_context("/"):
        seed_demo()
    db.dispose()  # checkpoints WAL so the single file holds everything
    return path


@pytest.fixture(scope="session")
def empty_template(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("template") / "empty.db"
    create_app(make_settings(path), FixedClock(REFERENCE_NOW))
    db.dispose()
    return path


def _app_from(template: Path, tmp_path: Path, **overrides):
    target = tmp_path / "test.db"
    shutil.copyfile(template, target)
    app = create_app(make_settings(target, **overrides), FixedClock(REFERENCE_NOW))
    app.config["TESTING"] = True
    return app


@pytest.fixture
def app(seeded_template, tmp_path):
    application = _app_from(seeded_template, tmp_path)
    yield application
    db.dispose()


@pytest.fixture
def empty_app(empty_template, tmp_path):
    application = _app_from(empty_template, tmp_path)
    yield application
    db.dispose()


class Api:
    """Test client wrapper that signs in and sends the CSRF header like the browser's api.js."""

    def __init__(self, flask_app, username: str | None, password: str = MOCK_PASSWORD):
        self.app = flask_app
        self.client = flask_app.test_client()
        self.csrf = None
        self.user = None
        if username is not None:
            self.login(username, password)

    def login(self, username, password):
        res = self.client.post("/api/v1/session", json={"username": username, "password": password})
        assert res.status_code == 200, res.get_json()
        self.csrf = res.get_json()["csrfToken"]
        self.user = res.get_json()["user"]
        return res

    def _headers(self, extra=None):
        headers = {"X-CSRF-Token": self.csrf} if self.csrf else {}
        headers.update(extra or {})
        return headers

    def get(self, url, headers=None, **kw):
        return self.client.get(url, headers=headers or {}, **kw)

    def post(self, url, json=None, headers=None):
        return self.client.post(url, json=json if json is not None else {}, headers=self._headers(headers))

    def put(self, url, json=None, headers=None):
        return self.client.put(url, json=json, headers=self._headers(headers))

    def patch(self, url, json=None, headers=None):
        return self.client.patch(url, json=json, headers=self._headers(headers))

    def delete(self, url, headers=None):
        return self.client.delete(url, headers=self._headers(headers))

    def json(self, url, status=200, headers=None):
        res = self.get(url, headers=headers)
        assert res.status_code == status, (res.status_code, res.get_json(silent=True))
        return res.get_json()


def _account(name):
    @pytest.fixture
    def fixture(app) -> Api:
        return Api(app, f"mock.{name}")
    return fixture


admin = _account("admin")          # SYS_ADMIN: everything
executive = _account("exec")       # EXECUTIVE: reads, reports, export
head = _account("head")            # DEPT_HEAD, Group 2 only
capability = _account("capability")  # CAPABILITY_MGR: requirements, models, assets
pm = _account("pm")                # PROJECT_MGR
viewer = _account("viewer")        # VIEWER: reads only


@pytest.fixture
def anon(app) -> Api:
    return Api(app, None)
