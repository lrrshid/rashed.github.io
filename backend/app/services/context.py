"""Small accessors shared by services: request-scoped DB session, clock, settings, company-local today."""
from __future__ import annotations

from datetime import date, datetime

from flask import current_app
from sqlalchemy.orm import Session

from ..core.clock import Clock
from ..core.config import Settings
from ..exceptions import StaleVersion
from ..extensions import db


def session() -> Session:
    return db.session()


def clock() -> Clock:
    return current_app.config["CLOCK"]


def settings() -> Settings:
    """The configuration in effect: the start-up settings with what Settings > connections manages (the sign-in
    method, the directory) laid over them (services/connections/config_service.py)."""
    from .connections.config_service import effective

    return effective()


def now() -> datetime:
    return clock().now()


def today() -> date:
    return clock().today(settings().zone)


def check_version(entity, supplied: int) -> None:
    """The client must send the version it last read; anything else means someone else saved first."""
    if entity.version != supplied:
        raise StaleVersion()


def stamp_create(entity, actor, at: datetime) -> None:
    entity.created_at = at
    entity.updated_at = at
    entity.created_by = actor.id
    entity.updated_by = actor.id


def stamp_update(entity, actor, at: datetime) -> None:
    entity.updated_at = at
    entity.updated_by = actor.id
