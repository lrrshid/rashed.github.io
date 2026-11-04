"""WSGI entry point.

Development:  flask --app wsgi run          (from the backend/ folder, or use scripts/run_dev.ps1)
Production:   waitress-serve --listen=127.0.0.1:8080 --ident= wsgi:app   (behind the company HTTPS proxy)
"""
import sys

from app import create_app
from app.core.config import ConfigError

try:
    app = create_app()
except ConfigError as exc:
    # A configuration or schema problem (missing ORACLE_* variable, schema behind the code): one clear line for the
    # operator instead of a traceback, for the server and for every `flask --app wsgi ...` command alike.
    sys.exit(f"Configuration error: {exc}")
