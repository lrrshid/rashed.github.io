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


# Roles and accounts only the tests have. The standard roles (reference_data.ROLES) are the organisation's structure:
# five with every permission, two that add and view. The permission rules are also tested with narrower shapes: read
# only with reports and export (mock.exec), a group-scoped role (mock.head, Group 2), one-area editors (capabilities,
# maintenance, testing), an analyst and a viewer. They are the demo's roles before 25 Nov 2026; the editing ones hold
# records.change (they change what exists, like before).
# code, English, Arabic, scope, permissions
TEST_ROLES = (
    ("EXECUTIVE", "Executive leadership", "القيادة التنفيذية", "ALL", ("view", "reports.view", "reports.exec", "export")),
    ("DEPT_HEAD", "Head of department", "رئيس المجموعة", "DEPARTMENT",
     ("view", "edit.requirements", "records.change", "reports.view", "reports.exec", "export")),
    ("CAPABILITY_MGR", "Capability manager", "مدير القدرات", "ALL",
     ("view", "edit.requirements", "edit.models", "edit.assets", "edit.documents", "records.change", "reports.view",
      "reports.exec", "reports.build", "export")),
    ("MAINTENANCE", "Maintenance team", "فريق الصيانة", "ALL",
     ("view", "edit.maintenance", "edit.documents", "records.change", "reports.view")),
    ("TESTING", "Testing team", "فريق التجارب", "ALL", ("view", "edit.testing", "edit.documents", "records.change",
                                                        "reports.view")),
    ("ANALYST", "Analyst", "محلل", "ALL", ("view", "reports.view", "reports.exec", "reports.build", "reports.schedule",
                                         "export")),
    ("VIEWER", "Viewer", "مطّلع", "ALL", ("view", "reports.view")),
)
# username, display name, role, department codes
TEST_ACCOUNTS = (
    ("mock.exec", "Mock Executive", "EXECUTIVE", ()),
    ("mock.head", "Mock Head of Group 2", "DEPT_HEAD", ("G2",)),
    ("mock.capability", "Mock Capability Manager", "CAPABILITY_MGR", ()),
    ("mock.maint", "Mock Maintenance Lead", "MAINTENANCE", ()),
    ("mock.test", "Mock Test Lead", "TESTING", ()),
    ("mock.analyst", "Mock Analyst", "ANALYST", ()),
    ("mock.viewer", "Mock Viewer", "VIEWER", ()),
)


def add_test_roles() -> None:
    """TEST_ROLES (not placed in the structure: level 0) and TEST_ACCOUNTS, after the demo world."""
    from sqlalchemy import select

    from app.models import AppRole, AppUser, Department, RolePermission
    from app.services import context, user_service

    session = context.session()
    now = context.now()
    for order, (code, en, ar, scope, permissions) in enumerate(TEST_ROLES, start=50):
        role = AppRole(code=code, name_en=en, name_ar=ar, scope=scope, is_system=0, sort_order=order, tier=0,
                       created_at=now, updated_at=now)
        role.permission_links = [RolePermission(permission=p, created_at=now) for p in permissions]
        session.add(role)
    session.commit()
    admin = session.scalar(select(AppUser).where(AppUser.username == "mock.admin"))
    for username, name, role, departments in TEST_ACCOUNTS:
        ids = [session.scalar(select(Department.id).where(Department.code == c)) for c in departments]
        user_service.create_user(username, name, role, MOCK_PASSWORD, actor=admin, department_ids=ids,
                                 note="Test account (mock password)")


@pytest.fixture(scope="session")
def seeded_template(tmp_path_factory) -> Path:
    from app.seed.demo_seeder import seed_demo

    path = tmp_path_factory.mktemp("template") / "seeded.db"
    app = create_app(make_settings(path), FixedClock(REFERENCE_NOW))
    with app.test_request_context("/"):
        seed_demo()
        add_test_roles()
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


# The organisation's structure (the demo accounts, reference_data.ROLES)
admin = _account("admin")          # SYS_ADMIN: everything
commander = _account("commander")  # COMMANDER: everything
capdev = _account("capdev")        # HEAD_CAP_DEV: everything
pm = _account("pm")                # PROJECT_MGR: adds and views
staff = _account("user")           # USER: adds and views
# Test-only shapes (TEST_ROLES above)
executive = _account("exec")       # EXECUTIVE: reads, reports, export
head = _account("head")            # DEPT_HEAD, Group 2 only
capability = _account("capability")  # CAPABILITY_MGR: requirements, models, assets
viewer = _account("viewer")        # VIEWER: reads only


@pytest.fixture
def anon(app) -> Api:
    return Api(app, None)
