"""User accounts and their role. Only a system administrator manages users through the API (routes use @admin_only);
the CLI and the demo seeder call create_user directly. There is no sign-up screen.

A user of a DEPARTMENT-scoped role is tied to one or more departments (user_department); ALL-scoped roles have none.
Users are deactivated, never deleted. Every change is written to the audit trail.
"""
from __future__ import annotations

import logging
import re

from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.orm import selectinload

from ..exceptions import Conflict, DirectoryUnavailable, Duplicate, NotFound, ValidationFailed
from ..models import ROLE_SYS_ADMIN, AppRole, AppSession, AppUser, Department, UserDepartment
from ..repositories import common as repo
from ..schemas.common import page_envelope
from ..schemas.dto import user_admin_dto
from ..security.auth import BREAK_GLASS_PASSWORD_NOTE, hash_password, require_admin, unusable_password_hash
from ..security.directory import get_directory, normalise_username
from ..security.mock_credentials import MOCK_PASSWORD
from . import audit_service, context

log = logging.getLogger("cpc.users")

DIRECTORY_ACCOUNT_NOTE = "Signs in with the company directory (Windows password)."
BREAK_GLASS_DISPLAY_NAME = "Emergency admin"
BREAK_GLASS_MIN_PASSWORD = 16
BREAK_GLASS_MANAGED_ON_SERVER = ("The emergency (break-glass) account is managed on the server with the "
                                 "set-break-glass-password command.")


def directory_username(username: str | None) -> str:
    """AUTH_MODE=ldap: the stored form of a directory username (U12345), or 400 when it is not one. The break-glass
    account is not a directory user: it is managed on the server (flask set-break-glass-password)."""
    settings = context.settings()
    name = normalise_username(username)
    if settings.is_break_glass(name):
        raise ValidationFailed.field("username", BREAK_GLASS_MANAGED_ON_SERVER)
    if not settings.username_matches_pattern(name):
        raise ValidationFailed.field("username", "Enter the person's Windows username, for example U12345.")
    return name


def directory_lookup(actor: AppUser, username: str | None) -> dict:
    """GET /users/directory-lookup: a person's display name from the company directory, so an ADMIN adding them
    does not have to type it. AUTH_MODE=ldap only."""
    require_admin(actor)
    if not context.settings().is_ldap:
        raise NotFound("Sign-in through the company directory is not switched on.")
    if not (username or "").strip():
        raise ValidationFailed.field("username", "This field is required.")
    name = directory_username(username)
    try:
        found = get_directory().lookup(name)
    except DirectoryUnavailable as exc:
        log.error("company directory unavailable at user lookup",
                  extra={"fields": {"username": name, "error": exc.detail, "hint": exc.hint}})
        raise
    if found is None:
        raise NotFound(f"{name} was not found in the company directory.")
    return {"username": found.username, "displayName": found.display_name,
            "alreadyAdded": find(found.username) is not None}


def _initial_password(password: str | None) -> str:
    """The password for a new account: the one given, else the MOCK password (demo and test profiles only)."""
    if password is not None:
        return password
    if context.settings().profile == "oracle":
        raise ValidationFailed.field("password", "A password is required (mock passwords are for the demo only).")
    return MOCK_PASSWORD


def _role(code: str) -> AppRole:
    role = context.session().scalar(select(AppRole).where(AppRole.code == code))
    if role is None:
        raise ValidationFailed.field("role", f"Unknown role {code}.")
    return role


def _check_departments(role: AppRole, department_ids: list[int], keep: frozenset[int] = frozenset()) -> list[Department]:
    """A DEPARTMENT-scoped role needs at least one department; an ALL-scoped role has none. A newly added department
    must be active; one the user already has (`keep`) only has to exist."""
    ids = list(dict.fromkeys(department_ids))
    if role.scope != "DEPARTMENT":
        if ids:
            raise ValidationFailed.field("departmentIds", "Only a department-scoped role is tied to departments.")
        return []
    if not ids:
        raise ValidationFailed.field("departmentIds", "Choose at least one department for this role.")
    session = context.session()
    out = []
    for department_id in ids:
        department = repo.get(session, Department, department_id, for_update=department_id not in keep)
        if department is None or (department.archived_at is not None and department_id not in keep):
            raise ValidationFailed.field("departmentIds", f"Department {department_id} is not an active department.")
        out.append(department)
    return out


def _set_departments(user: AppUser, departments: list[Department]) -> None:
    wanted = {d.id for d in departments}
    user.department_links[:] = [link for link in user.department_links if link.department_id in wanted]
    have = {link.department_id for link in user.department_links}
    now = context.now()
    for department in departments:
        if department.id not in have:
            user.department_links.append(UserDepartment(department_id=department.id, created_at=now))


# Plain ASCII only: look-alike characters (Cyrillic "і", fullwidth "ｅ", zero-width spaces) would let an account pass
# for another one in the Users list and the audit trail. Display names stay free text.
USERNAME_RE = re.compile(r"[A-Za-z0-9._@-]+")


def create_user(username: str, display_name: str | None, role: str, password: str | None,
                actor: AppUser | None = None, department_ids: list[int] | None = None,
                note: str | None = None, break_glass: bool = False) -> AppUser:
    """Create a user. password=None creates an account that can never log in with a stored password (unusable
    hash); the API instead passes the password through _initial_password first, except with AUTH_MODE=ldap, where
    people sign in with the company directory. `actor` defaults to the new user itself (bootstrap of the first
    account). `note` replaces the default audit note. The BREAK_GLASS_USERNAME account is refused in every mode
    (web and create-user): only set_break_glass_password creates it (break_glass=True)."""
    username = (username or "").strip()
    if not break_glass and context.settings().is_break_glass(username):
        raise ValidationFailed.field("username", BREAK_GLASS_MANAGED_ON_SERVER)
    display_name = (display_name or "").strip() or username
    role = (role or "").strip().upper()
    if not (2 <= len(username) <= 120):
        raise ValidationFailed.field("username", "Username must be 2 to 120 characters.")
    if not USERNAME_RE.fullmatch(username):
        raise ValidationFailed.field(
            "username", "Use only letters A-Z, digits and . _ - @ in a username (no spaces or accented letters).")
    if len(display_name) > 160:
        raise ValidationFailed.field("displayName", "Display name must be at most 160 characters.")
    if password is not None and len(password) < 8:
        raise ValidationFailed.field("password", "Password must be at least 8 characters.")
    departments = _check_departments(_role(role), department_ids or [])
    session = context.session()
    if session.scalar(select(AppUser).where(func.lower(AppUser.username) == username.lower())) is not None:
        raise Duplicate.field("username", f"Username {username} already exists.")
    at = context.now()
    user = AppUser(
        username=username,
        display_name=display_name,
        password_hash=hash_password(password) if password is not None else unusable_password_hash(),
        role_code=role,
        is_active=1,
        created_at=at,
        updated_at=at,
    )
    _set_departments(user, departments)
    session.add(user)
    session.flush()
    if note is None and password is None:
        note = "Account that cannot log in."
    audit_service.record(actor or user, "CREATE", user, None, audit_service.snapshot(user), note)
    session.commit()
    return user


def create_user_as_admin(actor: AppUser, data) -> dict:
    """POST /users. With AUTH_MODE=ldap: no password (400 if one is sent) and a directory username (U12345)."""
    require_admin(actor)
    if context.settings().is_ldap:
        if data.password is not None:
            raise ValidationFailed.field(
                "password", "Leave the password out: people sign in with their Windows password.")
        user = create_user(directory_username(data.username), data.display_name, data.role, None, actor=actor,
                           department_ids=data.department_ids, note=DIRECTORY_ACCOUNT_NOTE)
        return get_user(actor, user.id)
    password = _initial_password(data.password)
    user = create_user(data.username, data.display_name, data.role, password, actor=actor,
                       department_ids=data.department_ids)
    return get_user(actor, user.id)


def _load(user_id: int) -> AppUser:
    user = context.session().scalars(
        select(AppUser).where(AppUser.id == user_id).options(selectinload(AppUser.department_links))
    ).one_or_none()
    if user is None:
        raise NotFound(f"User {user_id} was not found.")
    return user


def _department_names() -> dict[int, Department]:
    return {d.id: d for d in context.session().scalars(select(Department))}


def get_user(actor: AppUser, user_id: int) -> dict:
    require_admin(actor)
    return user_admin_dto(_load(user_id), _department_names())


def list_users(actor: AppUser, q: str | None, page: int, size: int) -> dict:
    require_admin(actor)
    session = context.session()
    query = select(AppUser)
    count = select(func.count()).select_from(AppUser)
    if q:
        pattern = repo.like_pattern(q)
        match = or_(func.lower(AppUser.username).like(pattern, escape="\\"),
                    func.lower(AppUser.display_name).like(pattern, escape="\\"))
        query = query.where(match)
        count = count.where(match)
    total = session.scalar(count)
    rows = session.scalars(
        query.options(selectinload(AppUser.department_links)).order_by(AppUser.display_name, AppUser.id)
        .offset(page * size).limit(size)
    ).all()
    names = _department_names()
    return page_envelope([user_admin_dto(u, names) for u in rows], page, size, total)


def _other_active_admins(user: AppUser) -> int:
    return context.session().scalar(
        select(func.count()).select_from(AppUser)
        .where(AppUser.role_code == ROLE_SYS_ADMIN, AppUser.is_active == 1, AppUser.id != user.id))


def _lock_admins_and(*user_ids: int) -> None:
    """Lock every active ADMIN row plus the given users, in id order, before the last-ADMIN check reads them.
    On Oracle (READ COMMITTED) two admins demoting each other at the same moment would otherwise both see the
    other as still active and leave no ADMIN; with the lock the second waits and then re-reads committed rows.
    SQLite already runs writes one at a time (BEGIN IMMEDIATE) and ignores FOR UPDATE."""
    context.session().scalars(
        select(AppUser.id)
        .where(or_(and_(AppUser.role_code == ROLE_SYS_ADMIN, AppUser.is_active == 1), AppUser.id.in_(list(user_ids))))
        .order_by(AppUser.id).with_for_update()).all()


def update_user(actor: AppUser, user_id: int, data) -> dict:
    """PATCH /users/{id}: display name, role, active flag and (for a department-scoped role) the department list.
    Safeguards: you cannot change your own role or deactivate yourself, and the last active system administrator stays one."""
    require_admin(actor)
    session = context.session()
    _lock_admins_and(user_id, actor.id)
    user = _load(user_id)
    if data.version is not None:
        context.check_version(user, data.version)
    changes = data.changes()
    new_role = changes.get("role", user.role_code)
    new_active = changes.get("active", user.active)

    if user.id == actor.id and (new_role != user.role_code or not new_active):
        raise Conflict("You cannot change your own role or deactivate your own account.", code="SELF_CHANGE")
    if user.role_code == ROLE_SYS_ADMIN and user.active and (new_role != ROLE_SYS_ADMIN or not new_active) \
            and _other_active_admins(user) == 0:
        raise Conflict("This is the last active system administrator. Give another user that role first.", code="LAST_ADMIN")

    # Departments: an explicit list wins; a department-scoped role without one keeps the user's current ones; an
    # ALL-scoped role clears them. Departments the user already has are kept even if archived since.
    role = _role(new_role)
    if "department_ids" in changes:
        wanted_ids = changes["department_ids"] or []
    elif role.scope == "DEPARTMENT":
        wanted_ids = sorted(user.department_ids)
    else:
        wanted_ids = []
    departments = _check_departments(role, wanted_ids, frozenset(user.department_ids))

    before = audit_service.snapshot(user)
    if user.active and not new_active:
        _end_sessions(user)
    if "display_name" in changes:
        user.display_name = changes["display_name"]
    user.role_code = new_role
    user.is_active = 1 if new_active else 0
    _set_departments(user, departments)
    # Compare before flushing, then write once: one UPDATE, one version bump, and the audit's after-snapshot
    # carries the version the user really has.
    if audit_service.snapshot(user) != before:
        user.updated_at = context.now()
        session.flush()
        audit_service.record(actor, "UPDATE", user, before, audit_service.snapshot(user), data.reason)
    else:
        session.flush()
    session.commit()
    return user_admin_dto(_load(user_id), _department_names())


def _end_sessions(user: AppUser) -> None:
    """Deactivation signs the user out everywhere, in the same transaction. Otherwise a session left untouched
    while the user was inactive would work again if the user were reactivated within the session limits."""
    context.session().execute(delete(AppSession).where(AppSession.user_id == user.id))


def set_active(username: str, active: bool, actor: AppUser | None = None) -> AppUser:
    """CLI: deactivate or reactivate a user. Keeps the last-ADMIN safeguard."""
    session = context.session()
    user = find(username)  # ignoring letter case, like every other username lookup
    if user is None:
        raise NotFound(f"User {username} was not found.")
    _lock_admins_and(user.id)
    session.refresh(user)
    if bool(user.active) == bool(active):
        session.commit()
        return user  # nothing to change: no audit event (api-spec: a change that alters nothing writes none)
    if not active and user.role_code == ROLE_SYS_ADMIN and user.active and _other_active_admins(user) == 0:
        raise Conflict("This is the last active system administrator. Give another user that role first.", code="LAST_ADMIN")
    before = audit_service.snapshot(user)
    if not active:
        _end_sessions(user)
    user.is_active = 1 if active else 0
    user.updated_at = context.now()
    session.flush()
    # Without an acting ADMIN (a server-side command), say so, so the row never reads as the user changing themselves.
    audit_service.record(actor or user, "UPDATE", user, before, audit_service.snapshot(user),
                         None if actor else "Changed from the server command line (no acting ADMIN given).")
    session.commit()
    return user


def set_break_glass_password(password: str) -> tuple[AppUser, bool]:
    """CLI (flask set-break-glass-password): the one emergency local ADMIN, BREAK_GLASS_USERNAME. Creates it if
    missing (display name "Emergency admin") and sets its password. Both steps are audited; the hash never is.
    Open sessions of the account end: someone who signed in with the old password is signed out.
    Returns (user, created)."""
    name = context.settings().break_glass_username
    if not name:
        raise ValidationFailed.field("BREAK_GLASS_USERNAME", "Set BREAK_GLASS_USERNAME in ldap.env first "
                                                             "(for example cpc.breakglass).")
    if len(password) < BREAK_GLASS_MIN_PASSWORD:
        raise ValidationFailed.field("password", f"The break-glass password must be at least "
                                                 f"{BREAK_GLASS_MIN_PASSWORD} characters.")
    session = context.session()
    user = find(name)
    created = user is None
    if created:
        create_user(name, BREAK_GLASS_DISPLAY_NAME, ROLE_SYS_ADMIN, None, break_glass=True,
                    note="Emergency (break-glass) admin account, created from the server command line.")
        user = find(name)
    before = audit_service.snapshot(user)
    _end_sessions(user)
    user.password_hash = hash_password(password)
    user.updated_at = context.now()
    session.flush()
    # auth._check_break_glass_password looks for this row (actor = the account itself) before accepting the password.
    audit_service.record(user, "UPDATE", user, before, audit_service.snapshot(user), BREAK_GLASS_PASSWORD_NOTE)
    session.commit()
    return user, created


def find(username: str) -> AppUser | None:
    """By username, ignoring letter case (usernames are unique regardless of case)."""
    return context.session().scalar(select(AppUser).where(func.lower(AppUser.username) == username.lower()))
