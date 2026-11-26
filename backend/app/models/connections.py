"""Settings > connections: the company directory (LDAP) and the main database (ported from the Asset Availability
project's Settings tab; schema db/sqlite/V007 and db/oracle/V009).

A SettingProfile is one connection (the directory, a database). Its SettingRevisions are numbered versions: the
non-secret fields as JSON, the secrets encrypted (core/secretbox.py; the key is never in the database) and a
fingerprint of both. One revision is ACTIVE (the profile points at it), at most one is a DRAFT being edited; older ones
are SUPERSEDED and kept for rollback. SettingTest rows say what a test found for one fingerprint, so an edit makes
earlier results stale. ConnectionSetting holds the sign-in method and the configuration generation every process
watches (services/connections/config_service.py). The business rules stay in APP_SETTING (services/settings_service.py).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import UTCDateTime
from .base import ArchivableMixin, AuditedMixin, Base, IdType, id_column, user_fk

KINDS = ("LDAP", "DATABASE")
DRAFT, ACTIVE, SUPERSEDED, DISCARDED = "DRAFT", "ACTIVE", "SUPERSEDED", "DISCARDED"
OUTCOMES = ("PASSED", "WARNING", "FAILED", "SKIPPED")


class SettingProfile(AuditedMixin, ArchivableMixin, Base):
    __tablename__ = "setting_profile"

    id: Mapped[int] = id_column("setting_profile_seq")
    kind: Mapped[str] = mapped_column(String(10), nullable=False)
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    purpose: Mapped[str] = mapped_column(String(30), nullable=False)
    enabled: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 0 or 1, like APP_USER.is_active
    active_revision_id: Mapped[int | None] = mapped_column(IdType, ForeignKey("setting_revision.id", use_alter=True))


class SettingRevision(AuditedMixin, Base):
    __tablename__ = "setting_revision"

    id: Mapped[int] = id_column("setting_revision_seq")
    profile_id: Mapped[int] = mapped_column(IdType, ForeignKey("setting_profile.id"), nullable=False)
    revision_no: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(10), nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    fields_json: Mapped[str] = mapped_column(Text, nullable=False)
    secrets_json: Mapped[str | None] = mapped_column(Text)  # {"name": "<key id>:<base64 nonce+ciphertext>"}
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    note: Mapped[str | None] = mapped_column(String(500))

    @property
    def secret_names(self) -> str:
        """Which secrets are saved, for the audit trail: names only, never a value or its encrypted form."""
        import json

        return ",".join(sorted(json.loads(self.secrets_json))) if self.secrets_json else ""


class SettingTest(Base):
    __tablename__ = "setting_test"

    id: Mapped[int] = id_column("setting_test_seq")
    profile_id: Mapped[int] = mapped_column(IdType, ForeignKey("setting_profile.id"), nullable=False)
    revision_id: Mapped[int | None] = mapped_column(IdType, ForeignKey("setting_revision.id"))
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    stage: Mapped[str] = mapped_column(String(30), nullable=False)
    outcome: Mapped[str] = mapped_column(String(10), nullable=False)
    code: Mapped[str | None] = mapped_column(String(40))
    message: Mapped[str | None] = mapped_column(String(500))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    tested_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    tested_by: Mapped[int] = user_fk()


class SettingCert(AuditedMixin, ArchivableMixin, Base):
    __tablename__ = "setting_cert"

    id: Mapped[int] = id_column("setting_cert_seq")
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    pem: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    issuer: Mapped[str] = mapped_column(String(500), nullable=False)
    not_before: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    not_after: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)


class EgressRule(AuditedMixin, ArchivableMixin, Base):
    __tablename__ = "egress_rule"

    id: Mapped[int] = id_column("egress_rule_seq")
    host: Mapped[str] = mapped_column(String(253), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    purpose: Mapped[str] = mapped_column(String(10), nullable=False)
    note: Mapped[str | None] = mapped_column(String(500))


class ConnectionSetting(Base):
    """A few named values: SIGN_IN_METHOD (local | ldap) and CONFIG_GENERATION."""
    __tablename__ = "connection_setting"

    name: Mapped[str] = mapped_column(String(40), primary_key=True)
    value: Mapped[str] = mapped_column(String(500), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    updated_by: Mapped[int | None] = user_fk(nullable=True)
    version: Mapped[int] = mapped_column(BigInteger().with_variant(Integer(), "sqlite"), nullable=False, default=1)

    __mapper_args__ = {"version_id_col": version}


class ProcessHeartbeat(Base):
    __tablename__ = "process_heartbeat"

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    generation: Mapped[int] = mapped_column(BigInteger().with_variant(Integer(), "sqlite"), nullable=False)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
