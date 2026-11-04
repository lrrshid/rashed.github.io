"""Engine/session setup, dialect handling, SQLite migration runner and Oracle schema validation."""
from __future__ import annotations

import contextvars
import re
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from sqlalchemy import DateTime, create_engine, event, inspect
from sqlalchemy.dialects import oracle
from sqlalchemy.engine import Engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, scoped_session, sessionmaker
from sqlalchemy.sql.functions import FunctionElement
from sqlalchemy.types import TypeDecorator

from .config import ConfigError, Settings, sqlite_path

# When True, the next SQLite transaction on this context starts with BEGIN IMMEDIATE (takes the write
# lock up front). Set for POST/PATCH/DELETE requests and CLI writes; reads use a plain deferred BEGIN.
# Without this, a deferred transaction that reads and then writes fails under WAL with SQLITE_BUSY_SNAPSHOT.
_write_intent: contextvars.ContextVar[bool] = contextvars.ContextVar("write_intent", default=False)


def set_write_intent(value: bool) -> contextvars.Token:
    return _write_intent.set(value)


def reset_write_intent(token: contextvars.Token) -> None:
    _write_intent.reset(token)


@contextmanager
def write_intent() -> Iterator[None]:
    token = _write_intent.set(True)
    try:
        yield
    finally:
        _write_intent.reset(token)


class _UtcInstant(FunctionElement):
    """A selected TIMESTAMP WITH TIME ZONE column, read as its UTC instant (see UTCDateTime.column_expression)."""

    inherit_cache = True

    def __init__(self, expr, type_):
        super().__init__(expr)
        self.type = type_  # keeps UTCDateTime's result processing (tagging the value as UTC)


@compiles(_UtcInstant)
def _utc_instant_default(element, compiler, **kw):
    return compiler.process(element.clauses, **kw)


@compiles(_UtcInstant, "oracle")
def _utc_instant_oracle(element, compiler, **kw):
    return f"SYS_EXTRACT_UTC({compiler.process(element.clauses, **kw)})"


class UTCDateTime(TypeDecorator):
    """Aware-UTC datetimes in Python. SQLite: naive UTC text. Oracle: TIMESTAMP WITH TIME ZONE.

    python-oracledb binds datetimes without tzinfo, so values are converted to UTC and stripped before
    binding, and every Oracle session runs with TIME_ZONE='+00:00' (see _configure_oracle) so the stored
    instant is correct for anyone reading the table outside the application.

    Reading: thin mode returns a TIMESTAMP WITH TIME ZONE as the stored local time without its offset, so a value
    another tool wrote with, say, +04:00 would come back four hours off. On Oracle every selected column is therefore
    wrapped in SYS_EXTRACT_UTC(), which returns the UTC instant whatever offset it was stored with.
    """

    impl = DateTime
    cache_ok = True

    def column_expression(self, colexpr):
        return _UtcInstant(colexpr, type_=self)

    def load_dialect_impl(self, dialect):
        if dialect.name == "oracle":
            return dialect.type_descriptor(oracle.TIMESTAMP(timezone=True))
        return dialect.type_descriptor(DateTime())

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("UTCDateTime requires an aware datetime")
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is not None:
            return value.astimezone(timezone.utc)
        return value.replace(tzinfo=timezone.utc)


class Database:
    def __init__(self) -> None:
        self.engine: Engine | None = None
        self.session: scoped_session | None = None
        self._factory: sessionmaker | None = None
        self.schema: str | None = None

    def init(self, settings: Settings) -> None:
        if settings.is_sqlite:
            path = sqlite_path(settings)
            path.parent.mkdir(parents=True, exist_ok=True)
            engine = create_engine(
                settings.database_url,
                connect_args={"timeout": 5, "check_same_thread": False},
                hide_parameters=True,  # bound values (defect text, tokens) never appear in error messages/logs
            )
            _configure_sqlite(engine)
        else:
            kwargs = dict(
                connect_args=settings.oracle_connect_args,
                pool_size=settings.oracle_pool_max,
                max_overflow=0,
                pool_pre_ping=True,
                pool_timeout=10,
                hide_parameters=True,
            )
            if settings.oracle_thick_mode:
                kwargs["thick_mode"] = {"lib_dir": settings.oracle_client_lib_dir} if settings.oracle_client_lib_dir else {}
            engine = create_engine(settings.database_url, **kwargs)
            _configure_oracle(engine, settings.oracle_schema)
        self.schema = settings.oracle_schema if not settings.is_sqlite else None
        self.engine = engine
        self._factory = sessionmaker(bind=engine, expire_on_commit=False, autoflush=True)
        self.session = scoped_session(self._factory)

    def new_session(self) -> Session:
        """An independent session (not the request-scoped one). Caller must close it."""
        return self._factory()

    def remove(self) -> None:
        if self.session is not None:
            self.session.remove()

    def dispose(self) -> None:
        self.remove()
        if self.engine is not None:
            self.engine.dispose()


def _configure_sqlite(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_conn, _record):
        # Take over transaction control from the sqlite3 module so BEGIN is emitted by us (below).
        dbapi_conn.isolation_level = None
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute("PRAGMA journal_mode = WAL")
        cursor.execute("PRAGMA busy_timeout = 5000")
        cursor.close()
        # Unicode-aware LOWER(), matching the str.lower() used for search patterns (the built-in folds only A-Z).
        dbapi_conn.create_function("lower", 1, lambda s: s.lower() if isinstance(s, str) else s, deterministic=True)

    @event.listens_for(engine, "begin")
    def _on_begin(conn):
        conn.exec_driver_sql("BEGIN IMMEDIATE" if _write_intent.get() else "BEGIN")


def _configure_oracle(engine: Engine, schema: str | None) -> None:
    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_conn, _record):
        cursor = dbapi_conn.cursor()
        # A numeric offset, not the region name 'UTC': values bound into TIMESTAMP WITH TIME ZONE take the session
        # zone, and python-oracledb thin mode cannot read a stored region name (DPY-3022), only an offset.
        cursor.execute("ALTER SESSION SET TIME_ZONE = '+00:00'")
        if schema:
            # Least-privilege runtime user: resolve unqualified table/sequence names in the owner's schema.
            # `schema` is validated as a plain identifier in config.py (it cannot be a bind variable here).
            cursor.execute(f"ALTER SESSION SET CURRENT_SCHEMA = {schema}")
        cursor.close()


_VERSION_RE = re.compile(r"^V(\d+)__.+\.sql$")


def migrate_sqlite(engine: Engine, migrations_dir: Path) -> list[str]:
    """Apply db/sqlite/V*.sql scripts that have not run yet. Each script and its SCHEMA_VERSION row
    commit together. Returns the names of scripts applied."""
    scripts = []
    for path in migrations_dir.glob("V*__*.sql"):
        match = _VERSION_RE.match(path.name)
        if match:
            scripts.append((int(match.group(1)), path))
    scripts.sort()

    applied_now: list[str] = []
    raw = engine.raw_connection()
    try:
        conn = raw.driver_connection
        conn.execute(
            "CREATE TABLE IF NOT EXISTS SCHEMA_VERSION ("
            " version INTEGER PRIMARY KEY, script TEXT NOT NULL, applied_at TEXT NOT NULL)"
        )
        done = {row[0] for row in conn.execute("SELECT version FROM SCHEMA_VERSION")}
        for version, path in scripts:
            if version in done:
                continue
            body = path.read_text(encoding="utf-8")
            stamp = datetime.now(timezone.utc).isoformat()
            # Scripts that rebuild tables (SQLite cannot alter CHECK constraints in place) declare
            # "-- migrate: foreign-keys-off". Foreign keys are switched off around the transaction (the
            # pragma is ignored inside one) and the whole database is checked before committing.
            fk_off = "-- migrate: foreign-keys-off" in body
            try:
                if fk_off:
                    conn.execute("PRAGMA foreign_keys = OFF")
                # The version row is claimed first, under the write lock: if another process (a second server, a
                # CLI command starting at the same moment) applied this script after `done` was read, the insert
                # fails before the script runs, and this process skips it instead of failing to start.
                name = path.name.replace("'", "''")
                conn.executescript(
                    f"BEGIN IMMEDIATE;\nINSERT INTO SCHEMA_VERSION (version, script, applied_at)"
                    f" VALUES ({version}, '{name}', '{stamp}');\n{body}\n;"
                )
                problems = conn.execute("PRAGMA foreign_key_check").fetchall()
                if problems:
                    raise RuntimeError(f"{path.name} left {len(problems)} foreign-key violation(s); rolled back")
                conn.execute("COMMIT")
            except Exception:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                if conn.execute("SELECT 1 FROM SCHEMA_VERSION WHERE version = ?", (version,)).fetchone():
                    continue  # applied meanwhile by another process
                raise
            finally:
                if fk_off:
                    conn.execute("PRAGMA foreign_keys = ON")
            applied_now.append(path.name)
    finally:
        raw.close()
    return applied_now


def check_schema(engine: Engine, metadata, schema: str | None = None) -> None:
    """Fail fast if any mapped table or column is missing (used for Oracle instead of auto-create).
    `schema` is the owning schema when the app connects as a separate runtime user (ORACLE_SCHEMA)."""
    inspector = inspect(engine)
    existing = {name.lower() for name in inspector.get_table_names(schema=schema)}
    problems = []
    for table in metadata.sorted_tables:
        if table.name.lower() not in existing:
            problems.append(f"missing table {table.name}")
            continue
        columns = {col["name"].lower() for col in inspector.get_columns(table.name, schema=schema)}
        for column in table.columns:
            if column.name.lower() not in columns:
                problems.append(f"missing column {table.name}.{column.name}")
    if problems:
        raise ConfigError("Database schema does not match the application: " + "; ".join(problems))
