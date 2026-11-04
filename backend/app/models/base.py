from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Integer, Numeric, Sequence, String
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column

from ..core.database import UTCDateTime

# NUMBER(19,0) on Oracle; INTEGER (rowid alias, AUTOINCREMENT) on SQLite.
IdType = BigInteger().with_variant(Integer(), "sqlite")


class Base(DeclarativeBase):
    pass


def id_column(sequence_name: str) -> Mapped[int]:
    # The Sequence is used on Oracle and ignored on SQLite, which assigns ids itself.
    return mapped_column(IdType, Sequence(sequence_name, increment=1), primary_key=True)


def user_fk(nullable: bool = False) -> Mapped[int]:
    return mapped_column(IdType, ForeignKey("app_user.id"), nullable=nullable)


class AuditedMixin:
    """created/updated stamps and the optimistic-locking version shared by mutable business records."""

    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)

    @declared_attr
    def created_by(cls) -> Mapped[int]:
        return user_fk()

    @declared_attr
    def updated_by(cls) -> Mapped[int]:
        return user_fk()

    version: Mapped[int] = mapped_column(BigInteger().with_variant(Integer(), "sqlite"), nullable=False)

    @declared_attr.directive
    def __mapper_args__(cls):
        # SQLAlchemy adds "AND version = :old" to every UPDATE and bumps the number; a concurrent writer
        # that loses the race gets StaleDataError, mapped to 409 STALE_VERSION.
        return {"version_id_col": cls.__table__.c.version}


class ArchivableMixin:
    archived_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    @declared_attr
    def archived_by(cls) -> Mapped[int | None]:
        return user_fk(nullable=True)

    @property
    def is_archived(self) -> bool:
        return self.archived_at is not None


# Money (AED) and other fixed-precision figures: NUMBER(16,2) on Oracle, REAL on SQLite; plain floats in Python.
Money = Numeric(16, 2, asdecimal=False)


def code_column(length: int = 20) -> Mapped[str]:
    return mapped_column(String(length), nullable=False, unique=True)


class NamedMixin:
    """Bilingual name: every list entry and record shows its Arabic name in Arabic and its English name otherwise."""

    name_en: Mapped[str] = mapped_column(String(200), nullable=False)
    name_ar: Mapped[str] = mapped_column(String(200), nullable=False)
