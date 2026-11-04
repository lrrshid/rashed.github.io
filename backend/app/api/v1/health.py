"""GET /health: minimal public liveness + database check. No versions, hosts or error details."""
from __future__ import annotations

import logging

from flask import jsonify
from sqlalchemy import text

from ...extensions import db
from ...security.auth import public
from . import bp

log = logging.getLogger("cpc.health")


@bp.get("/health")
@public
def health():
    session = db.new_session()
    try:
        session.execute(text("SELECT 1 FROM DUAL" if db.engine.dialect.name == "oracle" else "SELECT 1"))
        return jsonify({"status": "UP"})
    except Exception:  # noqa: BLE001 - report DOWN, log the cause server-side only
        log.error("database health check failed", exc_info=True)
        return jsonify({"status": "DOWN"}), 503
    finally:
        session.close()
