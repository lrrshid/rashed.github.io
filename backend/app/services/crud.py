"""The one way business records are created, changed, archived and restored: permission and department scope
checked, created/updated stamps, optimistic-lock version, and an audit row in the same transaction.

Services describe their records and validate their own fields; this module does the bookkeeping."""
from __future__ import annotations

from sqlalchemy import func, select

from ..exceptions import Conflict, Duplicate, NotFound, ValidationFailed
from ..models import StatusDef
from ..repositories import common as repo
from ..security.auth import require_department_access, require_edit
from . import audit_service, context


def load(model, entity_id: int, actor, what: str, for_update: bool = False, department_of=None):
    """A record by id, or 404. Out-of-scope records (their department is not the user's) also answer 404."""
    entity = repo.get(context.session(), model, entity_id, for_update=for_update)
    if entity is None:
        raise NotFound(f"{what} {entity_id} was not found.")
    department_id = department_of(entity) if department_of else getattr(entity, "department_id", None)
    if department_id is not None:
        require_department_access(actor, department_id, f"{what} {entity_id} was not found.")
    return entity


def check_unique_code(model, code: str, exclude_id: int | None = None, field: str = "code") -> None:
    query = select(model.id).where(func.upper(model.code) == code.upper())
    if exclude_id is not None:
        query = query.where(model.id != exclude_id)
    if context.session().scalar(query) is not None:
        raise Duplicate.field(field, f"{code} is already used.")


def check_ref(model, entity_id: int | None, field: str, what: str, allow_archived: bool = False):
    """A referenced record must exist (and be active, unless it is already linked)."""
    if entity_id is None:
        return None
    entity = context.session().get(model, entity_id)
    if entity is None or (not allow_archived and getattr(entity, "archived_at", None) is not None):
        raise ValidationFailed.field(field, f"{what} {entity_id} is not an active {what.lower()}.")
    return entity


def check_status(domain: str, code: str | None, field: str = "status", current: str | None = None) -> None:
    """A status code must be one of the domain's active statuses (the current one may have been archived since)."""
    if code is None or code == current:
        return
    found = context.session().scalar(select(StatusDef).where(
        StatusDef.domain == domain, StatusDef.code == code, StatusDef.archived_at.is_(None)))
    if found is None:
        raise ValidationFailed.field(field, f"{code} is not a status of this list.")


def create(actor, entity, permission: str, department_id: int | None = None, reason: str | None = None,
           commit: bool = True):
    require_edit(actor, permission, department_id)
    session = context.session()
    context.stamp_create(entity, actor, context.now())
    session.add(entity)
    session.flush()
    audit_service.record(actor, "CREATE", entity, None, audit_service.snapshot(entity), reason)
    if commit:
        session.commit()
    return entity


def update(actor, entity, changes: dict, permission: str, version: int | None, reason: str | None = None,
           department_ids: tuple = (), commit: bool = True, extra_snapshot=None) -> bool:
    """Apply `changes` (attribute -> value). department_ids: departments the record is in before and after the change;
    the user needs both in scope. Returns whether anything changed (nothing changed: no audit row, no version bump)."""
    for department_id in department_ids or (getattr(entity, "department_id", None),):
        require_edit(actor, permission, department_id)
    if version is not None:
        context.check_version(entity, version)
    if getattr(entity, "archived_at", None) is not None:
        raise Conflict("This record is archived. Restore it before changing it.", code="ARCHIVED")
    session = context.session()
    before = audit_service.snapshot(entity)
    if extra_snapshot:
        before.update(extra_snapshot())
    for key, value in changes.items():
        setattr(entity, key, value)
    after = audit_service.snapshot(entity)
    if extra_snapshot:
        after.update(extra_snapshot())
    changed = after != before
    if changed:
        context.stamp_update(entity, actor, context.now())
        session.flush()
        after = audit_service.snapshot(entity)
        if extra_snapshot:
            after.update(extra_snapshot())
        audit_service.record(actor, "UPDATE", entity, before, after, reason)
    if commit:
        session.commit()
    return changed


def set_archived(actor, entity, archived: bool, permission: str, version: int | None, reason: str | None = None):
    require_edit(actor, permission, getattr(entity, "department_id", None))
    if version is not None:
        context.check_version(entity, version)
    if (entity.archived_at is not None) == archived:
        return entity
    session = context.session()
    before = audit_service.snapshot(entity)
    now = context.now()
    entity.archived_at = now if archived else None
    entity.archived_by = actor.id if archived else None
    context.stamp_update(entity, actor, now)
    session.flush()
    audit_service.record(actor, "ARCHIVE" if archived else "RESTORE", entity, before, audit_service.snapshot(entity),
                         reason)
    session.commit()
    return entity
