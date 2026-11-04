"""Structured JSON logs with a request id on every line. Never log passwords, cookies, DSNs or defect text."""
from __future__ import annotations

import json
import logging
import re
import sys
import time
import uuid
from datetime import datetime, timezone

from flask import Flask, g, has_request_context, request

_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "time": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if has_request_context():
            entry["requestId"] = getattr(g, "request_id", None)
        extra = getattr(record, "fields", None)
        if extra:
            entry.update(extra)
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


def configure_logging(app: Flask, level: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    app.logger.handlers[:] = []
    app.logger.propagate = True

    access = logging.getLogger("cpc.access")

    @app.before_request
    def _assign_request_id():
        incoming = request.headers.get("X-Request-ID", "")
        g.request_id = incoming if _REQUEST_ID_RE.match(incoming) else uuid.uuid4().hex
        g.request_started = time.perf_counter()

    @app.after_request
    def _log_request(response):
        response.headers["X-Request-ID"] = getattr(g, "request_id", "")
        if request.path.startswith("/api/"):
            user = getattr(g, "current_user", None)
            access.info(
                "request",
                extra={"fields": {
                    "method": request.method,
                    "path": request.path,  # path only: query strings may contain search text
                    "status": response.status_code,
                    "durationMs": round((time.perf_counter() - g.get("request_started", time.perf_counter())) * 1000, 1),
                    "userId": str(user.id) if user else None,
                }},
            )
        return response
