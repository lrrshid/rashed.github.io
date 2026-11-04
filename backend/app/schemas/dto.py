"""Response shapes shared by several routes. Ids are strings (browser integer precision); instants are ISO UTC."""
from __future__ import annotations

from ..core.clock import iso_utc
from ..models import AppUser


def sid(value) -> str | None:
    return None if value is None else str(value)


def record_meta(entity) -> dict:
    out = {"version": entity.version, "createdAt": iso_utc(entity.created_at), "updatedAt": iso_utc(entity.updated_at)}
    if hasattr(entity, "archived_at"):
        out["archived"] = entity.archived_at is not None
    return out


def session_user(user: AppUser, permissions: frozenset[str], scope: frozenset[int] | None) -> dict:
    role = user.role
    return {"id": sid(user.id), "username": user.username, "displayName": user.display_name,
            "role": user.role_code,
            "roleName": {"en": role.name_en, "ar": role.name_ar} if role else None,
            "permissions": sorted(permissions),
            "departmentIds": None if scope is None else [sid(i) for i in sorted(scope)]}


def user_admin_dto(user: AppUser, departments_by_id: dict) -> dict:
    """A user as the administrator's Users page sees it. Never includes the password hash."""
    linked = [departments_by_id[i] for i in sorted(user.department_ids) if i in departments_by_id]
    return {
        "id": sid(user.id),
        "username": user.username,
        "displayName": user.display_name,
        "role": user.role_code,
        "active": user.active,
        "departments": [{"id": sid(d.id), "code": d.code, "nameEn": d.name_en, "nameAr": d.name_ar} for d in linked],
        "createdAt": iso_utc(user.created_at),
        "updatedAt": iso_utc(user.updated_at),
        "version": user.version,
    }
