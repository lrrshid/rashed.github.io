"""The offline deployment (internet-to-local.md): the production server, the image, nginx and the guides agree with
the code. Nothing here needs Docker."""
from __future__ import annotations

import re
import threading
import urllib.request
from pathlib import Path

import pytest
from werkzeug.middleware.proxy_fix import ProxyFix

from app.api.v1.documents_alerts import UPLOAD_LIMIT
from serve import server_options

ROOT = Path(__file__).resolve().parents[3]
DEPLOYMENT = ROOT / "deployment"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------- the production server (backend/serve.py)

def test_server_defaults_and_validation():
    assert server_options({}) == dict(listen="127.0.0.1:8080", threads=8, ident="", channel_timeout=300,
                                      clear_untrusted_proxy_headers=True)
    behind = server_options({"APP_LISTEN": "0.0.0.0:8080", "APP_THREADS": "12", "TRUSTED_PROXY_COUNT": "1"})
    assert behind["listen"] == "0.0.0.0:8080" and behind["threads"] == 12
    assert behind["clear_untrusted_proxy_headers"] is False
    for bad in ({"APP_LISTEN": "8080"}, {"APP_THREADS": "0"}, {"APP_THREADS": "many"}, {"TRUSTED_PROXY_COUNT": "-1"}):
        with pytest.raises(ValueError, match=next(iter(bad))):
            server_options(bad)


def _client_address_seen(options: dict, forwarded_for: str) -> str:
    """Serve a tiny app the way the app is served (waitress + ProxyFix for one proxy) and return the address it sees."""
    from waitress.server import create_server

    def echo(environ, start_response):
        start_response("200 OK", [("Content-Type", "text/plain")])
        return [environ.get("REMOTE_ADDR", "").encode()]

    server = create_server(ProxyFix(echo, x_for=1, x_proto=1, x_host=1), **{**options, "listen": "127.0.0.1:0"})
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        request = urllib.request.Request(f"http://127.0.0.1:{server.effective_port}/",
                                         headers={"X-Forwarded-For": forwarded_for})
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.read().decode()
    finally:
        server.close()
        server.task_dispatcher.shutdown()


def test_behind_the_proxy_the_app_sees_each_users_address():
    # The sign-in throttle counts failures per client address. waitress's default removes X-Forwarded-For, so every
    # user would share nginx's address: serve.py keeps it when TRUSTED_PROXY_COUNT > 0.
    assert _client_address_seen(server_options({"TRUSTED_PROXY_COUNT": "1"}), "10.20.30.40") == "10.20.30.40"
    # With nothing in front, a browser's own X-Forwarded-For is dropped (the real peer address is used).
    assert _client_address_seen(server_options({}), "10.20.30.40") == "127.0.0.1"


# ---------------------------------------------------------------- image, proxy, settings

def test_image_takes_only_what_it_runs():
    lines = [l.strip() for l in _read(ROOT / ".dockerignore").splitlines() if l.strip() and not l.startswith("#")]
    assert lines[0] == "*"                                   # an allow-list: nothing new slips in by default
    assert {l for l in lines if l.startswith("!")} == {"!backend/", "!frontend/", "!db/"}
    assert "backend/tests/" in lines
    dockerfile = _read(ROOT / "predeployment" / "Dockerfile")
    assert "USER app" in dockerfile and 'CMD ["python", "serve.py"]' in dockerfile
    assert "/api/v1/health" in dockerfile


def test_nginx_admits_the_largest_upload_and_sets_the_forwarded_headers():
    conf = _read(DEPLOYMENT / "nginx" / "nginx.conf")
    size = re.search(r"client_max_body_size\s+(\d+)m;", conf)
    assert size and int(size.group(1)) * 1024 * 1024 >= UPLOAD_LIMIT
    # Replaced, never appended ($proxy_add_x_forwarded_for would let a browser choose its own address).
    assert "proxy_set_header X-Forwarded-For   $remote_addr;" in conf
    assert "$proxy_add_x_forwarded_for" not in conf
    assert "proxy_set_header X-Forwarded-Proto https;" in conf
    assert "proxy_pass http://cpc_app;" in conf and "server app:8080" in conf


def test_vm_settings_template_is_production_behind_one_proxy():
    env = dict(re.findall(r"^([A-Z_]+)=(.*)$", _read(DEPLOYMENT / "app.env.example"), re.M))
    assert env["APP_PROFILE"] == "oracle" and env["APP_ENV"] == "production"
    assert env["TRUSTED_PROXY_COUNT"] == "1"
    assert int(env["ORACLE_POOL_MAX"]) >= int(env["APP_THREADS"])   # one connection per busy thread
    compose = _read(DEPLOYMENT / "docker-compose.yml")
    app_service = compose.split("\n  proxy:")[0]
    assert not re.search(r"^\s+ports:", app_service, re.M)      # the app is reachable through nginx only
    assert "read_only: true" in app_service and "./data:/app/data" in app_service


def test_guides_name_the_latest_oracle_script():
    latest = max(p.name[:4] for p in (ROOT / "db" / "oracle").glob("V*.sql"))
    for guide in (DEPLOYMENT / "README.md", ROOT / "docs" / "IT_REQUEST.md", ROOT / "internet-to-local.md"):
        text = _read(guide)
        assert f"V001`…`{latest}" in text or f"V001`–`{latest}" in text or f"V001…{latest}" in text \
            or f"V001–{latest}" in text, f"{guide.name} does not name {latest} as the last Oracle script"


def test_secret_files_stay_out_of_git():
    ignored = _read(ROOT / ".gitignore")
    for pattern in ("dist/", "deployment/app.env", "deployment/data/", "deployment/backups/"):
        assert pattern in ignored, pattern
