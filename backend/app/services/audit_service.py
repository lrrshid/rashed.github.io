"""Append-only audit trail. record() adds the row to the caller's session so it commits or rolls back
together with the business change. There is deliberately no update or delete function.

Every change is logged with its previous and new values: snapshot() serialises every business column of a record
(never password hashes or the created/updated stamps), so the history shows exactly which field changed.
"""
from __future__ import annotations

import json
from datetime import date, datetime

from sqlalchemy import func, inspect as sa_inspect, select

from ..core.clock import iso_utc
from ..models import AuditEvent
from ..schemas.common import page_envelope
from . import context

# Never in a snapshot: secrets, and the stamps every change moves anyway.
_EXCLUDED = {"password_hash", "created_at", "updated_at", "created_by", "updated_by"}
# Extra (non-column) values some records add to their snapshot: link lists kept in child tables.
_EXTRA = {"APP_USER": ("department_ids_text",)}
_CONTEXT_KEYS = ("transition", "links")


def _plain(value):
    if isinstance(value, datetime):
        return iso_utc(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value) if value > 2**53 else value
    return value


def entity_type(entity) -> str:
    return entity.__table__.name.upper()


def snapshot(entity) -> dict:
    kind = entity_type(entity)
    out = {}
    for attr in sa_inspect(entity).mapper.column_attrs:
        name = attr.key
        if name in _EXCLUDED or name == "id":
            continue
        value = getattr(entity, name)
        # Ids are strings in every API response, including history (browser integer precision).
        out[name] = str(value) if name.endswith("_id") and value is not None else _plain(value)
    for name in _EXTRA.get(kind, ()):
        out[name] = getattr(entity, name)
    return out


def record(actor, action: str, entity, before: dict | None, after: dict | None, reason: str | None = None,
           extra: dict | None = None) -> AuditEvent:
    """Add an audit row to the current transaction. `extra` is merged into the after-snapshot (e.g. link changes)."""
    if after is not None and extra:
        after = {**after, **extra}
    event = AuditEvent(
        actor_id=actor.id,
        action=action,
        entity_type=entity_type(entity),
        entity_id=entity.id,
        occurred_at=context.now(),
        before_json=json.dumps(before, sort_keys=True) if before is not None else None,
        after_json=json.dumps(after, sort_keys=True) if after is not None else None,
        reason=reason,
    )
    context.session().add(event)
    return event


def changes(event: AuditEvent) -> list[dict]:
    """Field-level differences between before and after (`field`, `from`, `to`); the browser labels the fields."""
    before = json.loads(event.before_json) if event.before_json else {}
    after = json.loads(event.after_json) if event.after_json else {}
    out = []
    for key in sorted(set(before) | set(after)):
        if key == "version" or key in _CONTEXT_KEYS:
            continue
        old, new = before.get(key), after.get(key)
        if old != new:
            out.append({"field": key, "from": old, "to": new})
    return out


def event_dto(event: AuditEvent) -> dict:
    after = json.loads(event.after_json) if event.after_json else {}
    return {
        "id": str(event.id),
        "action": event.action,
        "entityType": event.entity_type,
        "entityId": str(event.entity_id),
        "occurredAt": iso_utc(event.occurred_at),
        "actor": {"id": str(event.actor.id), "displayName": event.actor.display_name},
        "reason": event.reason,
        "changes": changes(event),
        "context": {k: after[k] for k in _CONTEXT_KEYS if k in after},
    }


def entity_history(kind: str, entity_id: int) -> list[dict]:
    rows = context.session().scalars(
        select(AuditEvent)
        .where(AuditEvent.entity_type == kind, AuditEvent.entity_id == entity_id)
        .order_by(AuditEvent.occurred_at.desc(), AuditEvent.id.desc())
    ).all()
    return [event_dto(e) for e in rows]


def list_events(page: int, size: int, entity_type_filter: str | None, entity_id: int | None) -> dict:
    query = select(AuditEvent)
    count = select(func.count()).select_from(AuditEvent)
    if entity_type_filter:
        query = query.where(AuditEvent.entity_type == entity_type_filter)
        count = count.where(AuditEvent.entity_type == entity_type_filter)
    if entity_id is not None:
        query = query.where(AuditEvent.entity_id == entity_id)
        count = count.where(AuditEvent.entity_id == entity_id)
    session = context.session()
    total = session.scalar(count)
    rows = session.scalars(query.order_by(AuditEvent.occurred_at.desc(), AuditEvent.id.desc())
                           .offset(page * size).limit(size)).all()
    return page_envelope([event_dto(e) for e in rows], page, size, total)
