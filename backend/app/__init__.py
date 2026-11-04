"""Application factory: one Flask app serves the frontend and the /api/v1 endpoints."""
from __future__ import annotations

import mimetypes
from pathlib import Path

from flask import Flask, abort, request, send_from_directory
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.routing import IntegerConverter

from .core.clock import Clock, SystemClock
from .core.config import FRONTEND_DIR, SQLITE_MIGRATIONS_DIR, Settings, load_settings
from .core.database import check_schema, migrate_sqlite
from .core.logging import configure_logging
from .extensions import db
from .security.rate_limit import LoginThrottle

# Windows can map .js to text/plain from the registry; browsers refuse such module scripts.
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("image/svg+xml", ".svg")

# blob: in img-src and frame-src: a file chosen for a defect or a chat is shown before it is sent, from a blob: URL the
# page makes from the file on this computer (components/attachments.js). Only the page's own scripts can make one
# (script-src 'self'). object-src stays 'none': Edge shows a blob: PDF in the frame without it.
SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; "
        "frame-src 'self' blob:; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; "
        "form-action 'self'; frame-ancestors 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


class _IdConverter(IntegerConverter):
    def __init__(self, url_map, *args, **kwargs):
        kwargs.setdefault("min", 1)
        kwargs.setdefault("max", 9223372036854775807)
        super().__init__(url_map, *args, **kwargs)


def create_app(settings: Settings | None = None, clock: Clock | None = None, profile: str | None = None) -> Flask:
    settings = settings or load_settings(profile)
    app = Flask(__name__, static_folder=None)
    # Path ids are 1 .. 2^63-1 (api-spec 1.2). An id outside that range matches no route (JSON 404) instead of
    # reaching the database driver, which raises OverflowError (a 500) for anything beyond 64 bits.
    app.url_map.converters["int"] = _IdConverter
    app.config.update(
        SETTINGS=settings,
        CLOCK=clock or SystemClock(),
        LOGIN_THROTTLE=LoginThrottle(settings.login_max_failures, settings.login_window_seconds,
                                     settings.login_max_failures_per_ip),
        MAX_CONTENT_LENGTH=settings.max_content_length,
        JSON_SORT_KEYS=False,
    )
    app.json.sort_keys = False
    if settings.trusted_proxy_count > 0:
        n = settings.trusted_proxy_count
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=n, x_proto=n, x_host=n)

    configure_logging(app, settings.log_level)
    db.init(settings)
    _prepare_database(app, settings)

    from .api.v1 import bp as api_v1
    from .exceptions.handlers import register_error_handlers

    app.register_blueprint(api_v1)
    register_error_handlers(app)
    _register_frontend(app)

    @app.after_request
    def _security_headers(response):
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        if settings.cookie_secure:
            # HTTPS deployment: browsers stop trying plain HTTP for a year, so a typed http:// URL or old bookmark
            # cannot be downgraded. No includeSubDomains: other hosts on the company domain are not ours to force.
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.teardown_appcontext
    def _remove_session(_exc):
        db.remove()

    from .cli import register_cli

    register_cli(app)
    return app


def _prepare_database(app: Flask, settings: Settings) -> None:
    from .models import Base

    if settings.auto_migrate:
        migrate_sqlite(db.engine, SQLITE_MIGRATIONS_DIR)
    check_schema(db.engine, Base.metadata, db.schema)
    if settings.auto_seed:
        from .seed.demo_seeder import seed_if_empty

        with app.app_context():
            try:
                seed_if_empty()
            finally:
                # The request teardown that ends sessions is not registered yet: end this one here, or a read
                # after the seeder's last commit keeps the SQLite write lock and every request answers BUSY.
                db.remove()


def _register_frontend(app: Flask) -> None:
    """Static files plus a controlled HTML fallback: /api and missing asset files are real 404s; any other
    path returns index.html so deep links such as /stations/3 or /ships/7/defects/12 survive a refresh."""
    root = Path(FRONTEND_DIR)

    @app.get("/", defaults={"path": ""})
    @app.get("/<path:path>")
    def frontend(path: str):
        if path.startswith("api/") or path == "api":
            abort(404)
        if path:
            if any(part.startswith(".") for part in path.split("/")):
                abort(404)  # /.git/, /.env/...: no app page starts with a dot; never answer them with the app shell
            try:
                candidate = (root / path).resolve()
                is_file = root in candidate.parents and candidate.is_file()
            except (ValueError, OSError):  # e.g. an embedded NUL byte (%00)
                abort(404)
            if is_file:
                response = send_from_directory(root, path)
                response.headers["Cache-Control"] = "no-cache"
                return response
            if "." in path.rsplit("/", 1)[-1]:
                abort(404)  # looks like a file (has an extension) but does not exist
        response = send_from_directory(root, "index.html")
        response.headers["Cache-Control"] = "no-cache"
        return response
