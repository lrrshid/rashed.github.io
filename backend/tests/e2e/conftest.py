"""Real-browser fixtures: each test gets its own app server (fresh seeded SQLite file, free port) and a
Microsoft Edge page via Playwright. Run with:  pytest -m e2e

The server uses the real clock: the demo fixture is seeded relative to "today", so the baseline totals
(16 outstanding / 3 critical / 5 overdue) hold on the day the server starts.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]
ADMIN = ("e2e.admin", "e2e-admin-pass-1")          # role ADMIN
CEO = ("e2e.ceo", "e2e-ceo-pass-1")                # role CEO: reads everything, changes nothing
SUBMITTER = ("e2e.submitter", "e2e-submitter-pass-1")  # role TOP_SUBMITTER
# Seeded mock accounts (shared MOCK password): station submitters.
MOCK_PASSWORD = "Mock-Pass-123"
NORTH = ("mock.north", MOCK_PASSWORD)  # SUBMITTER on the North station only
EAST = ("mock.east", MOCK_PASSWORD)    # SUBMITTER on the East station only
VIEWPORTS = {"desktop": (1440, 900), "tablet": (768, 1024), "mobile": (390, 844)}


def pytest_collection_modifyitems(items):
    for item in items:
        if "/e2e/" in str(item.fspath).replace("\\", "/"):
            item.add_marker(pytest.mark.e2e)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Server:
    def __init__(self, tmp_path: Path):
        self.port = _free_port()
        self.db_path = tmp_path / "e2e.db"
        self.base_url = f"http://127.0.0.1:{self.port}"
        self.proc = None
        self.log_path = tmp_path / "server.log"

    def env(self) -> dict:
        env = {k: v for k, v in os.environ.items() if not k.startswith(("DEMO_", "APP_", "ORACLE_"))}
        env.update({
            "APP_PROFILE": "demo",
            "APP_ENV": "local",
            "APP_TIMEZONE": "Asia/Dubai",
            "LOG_LEVEL": "WARNING",
            "DEMO_DB_PATH": str(self.db_path),
            "DEMO_ADMIN_USERNAME": ADMIN[0],
            "DEMO_ADMIN_PASSWORD": ADMIN[1],
            "DEMO_ADMIN_DISPLAY_NAME": "E2E Admin",
            "DEMO_CEO_USERNAME": CEO[0],
            "DEMO_CEO_PASSWORD": CEO[1],
            "DEMO_CEO_DISPLAY_NAME": "E2E CEO",
            "DEMO_SUBMITTER_USERNAME": SUBMITTER[0],
            "DEMO_SUBMITTER_PASSWORD": SUBMITTER[1],
            "DEMO_SUBMITTER_DISPLAY_NAME": "E2E Submitter",
            "PYTHONDONTWRITEBYTECODE": "1",
        })
        return env

    def start(self) -> "Server":
        log = open(self.log_path, "w", encoding="utf-8")
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "waitress", f"--listen=127.0.0.1:{self.port}", "wsgi:app"],
            cwd=BACKEND, env=self.env(), stdout=log, stderr=subprocess.STDOUT,
        )
        deadline = time.time() + 30
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError(f"server exited early; see {self.log_path}")
            try:
                with urllib.request.urlopen(self.base_url + "/api/v1/health", timeout=1) as r:
                    if r.status == 200:
                        return self
            except OSError:
                time.sleep(0.2)
        raise RuntimeError("server did not become healthy in 30s")

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()

    def restart(self) -> None:
        """Stop and start on the same database file (persistence checks)."""
        self.stop()
        self.start()


@pytest.fixture
def server(tmp_path):
    srv = Server(tmp_path).start()
    yield srv
    srv.stop()


@pytest.fixture(scope="session")
def browser():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = p.chromium.launch(channel="msedge", headless=True)
        yield b
        b.close()


@pytest.fixture
def page(browser, server):
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    pg = context.new_page()
    pg.errors = []
    pg.on("pageerror", lambda e: pg.errors.append(str(e)))
    pg.on("console", lambda m: pg.errors.append(m.text) if m.type == "error" and "401" not in m.text and "status of 4" not in m.text else None)
    pg.base = server.base_url
    yield pg
    context.close()


def login(page, account=ADMIN, path="/stations"):
    page.goto(page.base + path)
    page.fill("#login-username", account[0])
    page.fill("#login-password", account[1])
    page.click("form.login-form button[type=submit]")
    page.wait_for_selector("#main h1:not(:text('Sign in'))")


def enable_edit_mode(page):
    toggle = page.get_by_role("button", name="Edit mode")
    if toggle.get_attribute("aria-pressed") != "true":
        toggle.click()
    page.wait_for_selector(".badge-editing")
