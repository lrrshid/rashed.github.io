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
    # The bundled nginx (a VM without nginx) and the site added to the VM's own nginx say the same.
    for path, upstream in ((DEPLOYMENT / "nginx" / "nginx.conf", ("proxy_pass http://cpc_app;", "server app:8080")),
                           (DEPLOYMENT / "nginx" / "cpc-site.conf.template",
                            ("proxy_pass http://cpc_portfolio_app;", "server 127.0.0.1:@APP_PORT@;"))):
        conf = _read(path)
        size = re.search(r"client_max_body_size\s+(\d+)m;", conf)
        assert size and int(size.group(1)) * 1024 * 1024 >= UPLOAD_LIMIT, path.name
        # Replaced, never appended ($proxy_add_x_forwarded_for would let a browser choose its own address).
        assert "proxy_set_header X-Forwarded-For   $remote_addr;" in conf, path.name
        assert "$proxy_add_x_forwarded_for" not in conf, path.name
        assert "proxy_set_header X-Forwarded-Proto https;" in conf, path.name
        assert all(part in conf for part in upstream), path.name


def test_the_installer_fills_every_placeholder_of_the_nginx_site():
    template = _read(DEPLOYMENT / "nginx" / "cpc-site.conf.template")
    install = _read(DEPLOYMENT / "install.sh")
    placeholders = set(re.findall(r"@[A-Z_]+@", template))
    assert placeholders >= {"@SERVER_NAME@", "@HTTPS_PORT@", "@APP_PORT@", "@CERT@", "@KEY@"}
    for placeholder in placeholders:
        assert f"s|{placeholder}|" in install, placeholder
    # Works on the nginx of older distributions: no http2 directive, a cache zone name of its own.
    directives = " ".join(line for line in template.splitlines() if not line.lstrip().startswith("#"))
    assert "http2" not in directives and "shared:CPC_PORTFOLIO_SSL:" in directives
    assert "nginx -t" in install  # the VM's nginx is reloaded only with a configuration it accepts


def test_vm_settings_are_production_behind_one_proxy():
    env = dict(re.findall(r"^([A-Z_]+)=(.*)$", _read(DEPLOYMENT / "app.env.example"), re.M))
    assert env["APP_ENV"] == "production" and env["TRUSTED_PROXY_COUNT"] == "1"
    assert env["APP_PROFILE"] == "demo" and env["DEMO_DB_PATH"].startswith("/app/data/")  # built-in, in the data folder
    assert "# ORACLE_POOL_MAX=8" in _read(DEPLOYMENT / "app.env.example")                   # Oracle: the other block
    install = _read(DEPLOYMENT / "install.sh")
    for line in ("APP_ENV=production", "TRUSTED_PROXY_COUNT=1", "APP_PROFILE=demo", "APP_PROFILE=oracle"):
        assert f'echo "{line}"' in install, line
    # The app container: published on the VM's loopback only (nginx is the way in), read-only, data in a host folder.
    start = install.index('docker run -d --name "$CONTAINER"')
    run = install[start:install.index('"cpc:$VERSION" >/dev/null', start)]
    assert re.findall(r'-p "([^"]+)"', run) == ["127.0.0.1:$APP_PORT:8080"]
    assert "--read-only" in run and "/app/data" in run and "--cap-drop ALL" in run


def test_the_kit_needs_nothing_from_the_internet_and_asks_no_secret_on_the_command_line():
    for name in ("install.sh", "scripts/app.sh"):
        script = _read(DEPLOYMENT / name)
        for banned in ("docker pull", "wget ", "apt-get", "yum ", "dnf ", "pip install", "http://", "--password "):
            assert banned not in script.replace("http://127.0.0.1", "").replace("http://cpc_portfolio_app", ""), \
                (name, banned)
        for line in script.splitlines():
            if re.search(r"(^|\s)curl\s+-", line):
                assert "--resolve" in line and "127.0.0.1" in line, line  # only to check the site on this VM
    install = _read(DEPLOYMENT / "install.sh")
    assert "--password-stdin" in install and "docker load -i" in install
    assert "sha256sum --quiet -c SHA256SUMS" in install


def test_the_kit_keeps_its_scripts_executable(tmp_path):
    import importlib.util
    import tarfile

    spec = importlib.util.spec_from_file_location("pack", ROOT / "predeployment" / "pack.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    pack = module.pack

    kit = tmp_path / "cpc-test"
    (kit / "scripts").mkdir(parents=True)
    (kit / "install.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    (kit / "scripts" / "app.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    (kit / "README.md").write_text("# kit\n", encoding="utf-8")
    pack(kit, tmp_path / "kit.tar.gz")
    with tarfile.open(tmp_path / "kit.tar.gz") as tar:
        modes = {m.name: (m.mode, m.uid) for m in tar.getmembers()}
    assert modes["cpc-test/install.sh"] == (0o755, 0) and modes["cpc-test/scripts/app.sh"] == (0o755, 0)
    assert modes["cpc-test/README.md"] == (0o644, 0) and modes["cpc-test"][0] == 0o755


def test_guides_name_the_latest_oracle_script():
    latest = max(p.name[:4] for p in (ROOT / "db" / "oracle").glob("V*.sql"))
    for guide in (DEPLOYMENT / "README.md", ROOT / "docs" / "IT_REQUEST.md", ROOT / "internet-to-local.md"):
        text = _read(guide)
        assert f"V001`…`{latest}" in text or f"V001`–`{latest}" in text or f"V001…{latest}" in text \
            or f"V001–{latest}" in text, f"{guide.name} does not name {latest} as the last Oracle script"


def test_secret_files_stay_out_of_git():
    ignored = _read(ROOT / ".gitignore")
    for pattern in ("dist/", "deployment/app.env", "deployment/data/", "deployment/backups/", "deployment/certs/*",
                    "deployment/install.conf"):
        assert pattern in ignored, pattern
