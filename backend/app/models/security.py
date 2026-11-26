"""Accounts, roles, permissions, sessions, department scope, audit history, business-rule settings, saved views."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.database import UTCDateTime
from .base import AuditedMixin, Base, IdType, id_column

ROLE_SYS_ADMIN = "SYS_ADMIN"  # the role of the break-glass account; also the seeded system administrator


class RolePermission(Base):
    __tablename__ = "role_permission"

    role_id: Mapped[int] = mapped_column(IdType, ForeignKey("app_role.id"), primary_key=True)
    permission: Mapped[str] = mapped_column(String(30), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)


class AppRole(Base):
    """A role: a named set of permissions and a scope (ALL departments, or the user's DEPARTMENTs)."""

    __tablename__ = "app_role"

    id: Mapped[int] = id_column("app_role_seq")
    code: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    name_en: Mapped[str] = mapped_column(String(120), nullable=False)
    name_ar: Mapped[str] = mapped_column(String(120), nullable=False)
    scope: Mapped[str] = mapped_column(String(20), nullable=False, default="ALL")
    is_system: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Level in the organisation's hierarchy (Settings > Roles): 1 at the top, roles of one level side by side, 0 = not
    # placed. Shown only; what a role may do is its permissions.
    tier: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    version: Mapped[int] = mapped_column(BigInteger().with_variant(Integer(), "sqlite"), nullable=False)

    permission_links: Mapped[list[RolePermission]] = relationship(
        RolePermission, cascade="all, delete-orphan", order_by=RolePermission.permission)

    __mapper_args__ = {"version_id_col": version}

    @property
    def permissions(self) -> frozenset[str]:
        return frozenset(link.permission for link in self.permission_links)


class UserDepartment(Base):
    """A department a DEPARTMENT-scoped user may see and change. Users of ALL-scoped roles need no rows."""

    __tablename__ = "user_department"

    user_id: Mapped[int] = mapped_column(IdType, ForeignKey("app_user.id"), primary_key=True)
    department_id: Mapped[int] = mapped_column(IdType, ForeignKey("department.id"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)


class AppUser(Base):
    """Login account. Users are deactivated (is_active=0), never deleted."""

    __tablename__ = "app_user"

    id: Mapped[int] = id_column("app_user_seq")
    username: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role_code: Mapped[str] = mapped_column(String(30), ForeignKey("app_role.code"), nullable=False)
    is_active: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    version: Mapped[int] = mapped_column(BigInteger().with_variant(Integer(), "sqlite"), nullable=False)

    # expunge: the signed-in user is detached from its session with its role and permissions (security/auth.py).
    role: Mapped[AppRole] = relationship(AppRole, lazy="selectin", cascade="save-update, merge, expunge")
    department_links: Mapped[list[UserDepartment]] = relationship(
        UserDepartment, cascade="all, delete-orphan", order_by=UserDepartment.department_id)

    __mapper_args__ = {"version_id_col": version}

    @property
    def active(self) -> bool:
        return bool(self.is_active)

    @property
    def permissions(self) -> frozenset[str]:
        return self.role.permissions if self.role is not None else frozenset()

    @property
    def department_ids(self) -> frozenset[int]:
        return frozenset(link.department_id for link in self.department_links)

    @property
    def department_ids_text(self) -> str | None:
        """Sorted comma-separated department ids, for the audit snapshot (None when there are none)."""
        return ",".join(str(i) for i in sorted(self.department_ids)) or None


class AppSession(Base):
    """Server-side login session. `id` is the SHA-256 hex digest of the cookie token."""

    __tablename__ = "app_session"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(IdType, ForeignKey("app_user.id"), nullable=False)
    csrf_token: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    # When the person last typed their password again: sensitive Settings steps need it within the last minutes
    # (security/auth.py require_recent_reauth).
    reauth_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class AuditEvent(Base):
    """Append-only history row. Written in the same transaction as the change it describes."""

    __tablename__ = "audit_event"

    id: Mapped[int] = id_column("audit_event_seq")
    actor_id: Mapped[int] = mapped_column(IdType, ForeignKey("app_user.id"), nullable=False)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    entity_id: Mapped[int] = mapped_column(IdType, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    before_json: Mapped[str | None] = mapped_column(Text)
    after_json: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)

    actor: Mapped[AppUser] = relationship(lazy="joined", innerjoin=True)


class ActionLog(Base):
    """User tracking (services/tracking_service.py): one row per action a person took, carried out or refused.
    Append-only. Who (as they were then), what, on which record, the outcome and why it failed, when and from where.
    For a change that was carried out, audit_event_id points at its first audit row (the fields that changed)."""

    __tablename__ = "action_log"

    id: Mapped[int] = id_column("action_log_seq")
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    user_id: Mapped[int | None] = mapped_column(IdType, ForeignKey("app_user.id"))
    username: Mapped[str] = mapped_column(String(120), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(160))
    role_code: Mapped[str | None] = mapped_column(String(30))
    action: Mapped[str] = mapped_column(String(30), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(40))
    entity_id: Mapped[int | None] = mapped_column(IdType)
    record_code: Mapped[str | None] = mapped_column(String(120))
    record_name_en: Mapped[str | None] = mapped_column(String(200))
    record_name_ar: Mapped[str | None] = mapped_column(String(200))
    outcome: Mapped[str] = mapped_column(String(10), nullable=False)  # DONE | FAILED
    http_status: Mapped[int] = mapped_column(Integer, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(40))
    error_message: Mapped[str | None] = mapped_column(String(300))
    error_fields: Mapped[str | None] = mapped_column(String(300))
    detail: Mapped[str | None] = mapped_column(String(300))
    audit_event_id: Mapped[int | None] = mapped_column(IdType, ForeignKey("audit_event.id"))
    changes_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    method: Mapped[str] = mapped_column(String(10), nullable=False)
    path: Mapped[str] = mapped_column(String(300), nullable=False)
    client_ip: Mapped[str | None] = mapped_column(String(64))
    request_id: Mapped[str | None] = mapped_column(String(64))
    preview_role: Mapped[str | None] = mapped_column(String(30))


class AppSetting(AuditedMixin, Base):
    """A business rule as JSON (services/settings_service.py documents each key)."""

    __tablename__ = "app_setting"

    id: Mapped[int] = id_column("app_setting_seq")
    setting_key: Mapped[str] = mapped_column(String(60), nullable=False, unique=True)
    value_json: Mapped[str] = mapped_column(Text, nullable=False)


class SavedView(Base):
    __tablename__ = "saved_view"

    id: Mapped[int] = id_column("saved_view_seq")
    user_id: Mapped[int] = mapped_column(IdType, ForeignKey("app_user.id"), nullable=False)
    page: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    filters_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
