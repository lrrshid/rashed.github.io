"""WSGI entry point.

Development:  flask --app wsgi run          (from the backend/ folder, or use scripts/run_dev.ps1)
Production:   python serve.py   (waitress behind the HTTPS proxy; APP_LISTEN, APP_THREADS, TRUSTED_PROXY_COUNT;
              the Docker image runs exactly this, see internet-to-local.md)
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
