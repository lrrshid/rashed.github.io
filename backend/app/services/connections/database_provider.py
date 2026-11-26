"""The main database as a Settings connection: stage, test, then restart (ported from the Asset Availability project;
owner choice, 24 Nov 2026: "exactly like the reference", and the new database starts clean).

The running database connection stays in .env: the app needs it to load everything else, and a database that is down
must never hide how to reach it (never store the only information needed to connect to a database inside that same
database). Settings shows that running connection read-only with its health (running()), and stages a candidate for a
planned restart. A candidate is tested with read-only checks only, never a migration, a copy, a write or any SQL an
admin typed, and the stages stop at the first failure:
  CONNECT      the server is an approved destination, answers a harmless query, and says who it is
  SCHEMA       every table and column this app maps is there (SQLite: and its SCHEMA_VERSION is this app's)
  PERMISSIONS  the account may do what the app does. Oracle: the runtime grants (db/oracle/runtime-grants.sql) as
               ALL_TAB_PRIVS shows them, and a `SELECT 1 FROM <table> WHERE 1 = 0` of each table; SQLite: the file and
               its folder are writable
  DATA         a clean start (owner, 24 Nov 2026): the new database must hold NO demo data. The demo world is made by
               the demo accounts (mock.*, every demo record names one as its creator), so any mock.* account fails the
               stage. An empty database passes (the administrator and the standard lists are made after the restart
               with `flask setup-database`); a database with accounts needs an active system administrator.
"Stage for restart" (apply) records the tested revision and changes nothing in the running app. The page then shows
the .env lines and the cutover steps; after the restart, the running connection is compared with the staged one.
Engines: Oracle (production) and SQLite (a file in data/, demo and test profiles only).
"""
from __future__ import annotations

import os
import re
import sqlite3
import ssl
import time

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.pool import NullPool

from ...core.config import DATA_DIR, PROJECT_ROOT, ConfigError, Settings, sqlite_path
from ...core.database import _VERSION_RE, check_schema
from . import egress
from .ldap_provider import StageResult, _ms, _redact
from .registry import SUPPORTED, Field, Provider, register

CONNECT, SCHEMA, PERMISSIONS, DATA = "CONNECT", "SCHEMA", "PERMISSIONS", "DATA"
STAGES = (CONNECT, SCHEMA, PERMISSIONS, DATA)
GRANTS_FILE = PROJECT_ROOT / "db" / "oracle" / "runtime-grants.sql"
_GRANT = re.compile(r"^\s*GRANT\s+([A-Z ,]+?)\s+ON\s+([A-Za-z0-9_$#]+)\s+TO\s+\S+?\s*;", re.IGNORECASE | re.MULTILINE)
COUNTED = ("app_user", "department", "capability_model", "asset", "project", "test_event")
SETUP_COMMAND = "flask --app wsgi setup-database --admin <username>"


def _oracle_check(values: dict, complete: bool) -> list[dict]:
    if complete and values.get("protocol") == "tcps" and not values.get("caCertIds"):
        return [{"field": "caCertIds", "message": "Choose the CA certificate that signed the database server's "
                                                  "certificate (upload it under Network and certificates)."}]
    return []


ORACLE = register(Provider(
    kind="DATABASE", id="oracle", purposes=("PRIMARY",), status=SUPPORTED, schema_version=1,
    fields=(
        Field("host", "host", required=True),
        Field("port", "int", default=1521, low=1, high=65535),
        Field("serviceName", "service", required=True),
        Field("protocol", "choice", default="tcp", choices=("tcp", "tcps")),
        Field("caCertIds", "certs"),  # required for tcps (_oracle_check)
        Field("username", "identifier", required=True),
        Field("schema", "identifier"),
        Field("timeoutSeconds", "int", default=10, low=1, high=60, advanced=True),
    ),
    secrets=("password",), required_secrets=("password",),
    stages=STAGES, required_stages=STAGES, restart_required=True, check=_oracle_check,
))

SQLITE = register(Provider(
    kind="DATABASE", id="sqlite", purposes=("PRIMARY",), status=SUPPORTED, schema_version=1,
    fields=(Field("fileName", "filename", required=True),),
    stages=STAGES, required_stages=STAGES, restart_required=True, app_profiles=("demo", "test"),
))


def destinations(provider_id: str, values: dict) -> list[tuple[str, int]]:
    return [(values["host"], values.get("port", 1521))] if provider_id == "oracle" and values.get("host") else []


def candidate(provider: Provider, values: dict, secrets: dict, pems: list[str], rules: tuple) -> dict:
    if provider.id == "sqlite":
        return {"engine": "sqlite", "path": DATA_DIR / values["fileName"], "name": values["fileName"]}
    return {"engine": "oracle", "host": values["host"], "port": values.get("port", 1521),
            "service": values["serviceName"], "protocol": values.get("protocol", "tcp"), "user": values["username"],
            "password": secrets.get("password"), "schema": values.get("schema"),
            "timeout": values.get("timeoutSeconds", 10), "pems": pems, "rules": rules}


def dsn(values: dict) -> str:
    """The Easy Connect string of an Oracle candidate (its fields as Settings stores them)."""
    base = f"{values['host']}:{values.get('port', 1521)}/{values['serviceName']}"
    return f"tcps://{base}" if values.get("protocol") == "tcps" else base


def _norm_dsn(value: str) -> str:
    value = value.strip().lower()
    return value[6:] if value.startswith("tcp://") else value


def candidate_key(provider_id: str, values: dict) -> str | None:
    """Which database a candidate points at, comparable with running_key()."""
    if provider_id == "sqlite" and values.get("fileName"):
        return "sqlite:" + str((DATA_DIR / values["fileName"]).resolve()).lower()
    if provider_id == "oracle" and values.get("host") and values.get("serviceName") and values.get("username"):
        user = values["username"].upper()
        return f"oracle:{_norm_dsn(dsn(values))}|{user}|{(values.get('schema') or user).upper()}"
    return None


def running_key(settings: Settings) -> str:
    if settings.is_sqlite:
        return "sqlite:" + str(sqlite_path(settings).resolve()).lower()
    args = settings.oracle_connect_args
    user = str(args.get("user", "")).upper()
    return f"oracle:{_norm_dsn(str(args.get('dsn', '')))}|{user}|{(settings.oracle_schema or user).upper()}"


def expected_version(engine_name: str) -> int:
    folder = PROJECT_ROOT / "db" / engine_name
    numbers = [int(m.group(1)) for p in folder.glob("V*.sql") if (m := _VERSION_RE.match(p.name))]
    return max(numbers, default=0)


def env_lines(provider_id: str, values: dict) -> list[str]:
    """What the server's .env (app.env on the Docker VM) says after the cutover. The password is never shown: the
    admin types it. The oracle profile also needs SETTINGS_KEY (the demo keeps its key in data/settings.key)."""
    if provider_id == "sqlite":
        return ["APP_PROFILE=demo", f"DEMO_DB_PATH=data/{values.get('fileName', '')}"]
    lines = ["APP_PROFILE=oracle", f"ORACLE_DSN={dsn(values)}", f"ORACLE_USER={values.get('username', '')}",
             "ORACLE_PASSWORD=<the password saved in Settings: type it yourself>"]
    if values.get("schema"):
        lines.append(f"ORACLE_SCHEMA={values['schema']}")
    lines.append(f"ORACLE_TIMEOUT_SECONDS={values.get('timeoutSeconds', 10)}")
    if values.get("protocol") == "tcps":
        lines.append("ORACLE_WALLET_LOCATION=<a folder holding the CA certificate saved as ewallet.pem>")
    lines.append("SETTINGS_KEY=<keep the current key (on the demo: the line in data/settings.key)>")
    return lines


def required_grants() -> dict[str, set[str]] | None:
    """{object name (upper): {privileges}} from db/oracle/runtime-grants.sql, or None when it is not on this server."""
    try:
        script = GRANTS_FILE.read_text(encoding="utf-8")
    except OSError:
        return None
    grants: dict[str, set[str]] = {}
    for privileges, obj in _GRANT.findall(script):
        grants.setdefault(obj.upper(), set()).update(p.strip().upper() for p in privileges.split(",") if p.strip())
    return grants


# ---- engines -------------------------------------------------------------------------------------------------------

def _engine(c: dict) -> Engine:
    """A throw-away engine for one test (no pool), read-only where the engine allows it."""
    if c["engine"] == "sqlite":
        uri = f"{c['path'].resolve().as_uri()}?mode=ro"  # read-only: a test never creates or changes the file
        return create_engine("sqlite://", poolclass=NullPool, hide_parameters=True,
                             creator=lambda: sqlite3.connect(uri, uri=True, timeout=5, check_same_thread=False))
    args = {"user": c["user"], "password": c["password"], "dsn": dsn({"host": c["host"], "port": c["port"],
                                                                         "serviceName": c["service"],
                                                                         "protocol": c["protocol"]}),
            "tcp_connect_timeout": c["timeout"]}
    if c["protocol"] == "tcps" and c["pems"]:
        args["ssl_context"] = ssl.create_default_context(cadata="\n".join(c["pems"]))
    engine = create_engine("oracle+oracledb://", connect_args=args, poolclass=NullPool, hide_parameters=True)
    schema, call_ms = c["schema"], c["timeout"] * 1000

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_conn, _record):
        dbapi_conn.call_timeout = call_ms  # no test query waits longer than the timeout
        cursor = dbapi_conn.cursor()
        cursor.execute("ALTER SESSION SET TIME_ZONE = '+00:00'")
        if schema:  # validated as a plain identifier (registry "identifier")
            cursor.execute(f"ALTER SESSION SET CURRENT_SCHEMA = {schema}")
        cursor.close()
    return engine


def _error(exc: Exception) -> str:
    inner = getattr(exc, "orig", None) or exc  # SQLAlchemy wraps the driver's error with the statement; keep the error
    return _redact(f"{type(inner).__name__}: {inner}")


def _hint(text_: str) -> str | None:
    lower = text_.lower()
    if "ora-01017" in lower or "invalid username/password" in lower:
        return "The username or password is wrong, or the account is locked (ask the DBA)."
    if "ora-12514" in lower or "dpy-6001" in lower or "service" in lower and "not" in lower:
        return "The server answered but does not know this service name: check it with the DBA."
    if "timed out" in lower or "dpy-6005" in lower or "refused" in lower or "unreachable" in lower:
        return "The server did not answer: check the server name, the port and the firewall."
    if "certificate" in lower or "ssl" in lower:
        return "The server's certificate is not trusted by the chosen CA certificate, or tcps is not enabled there."
    if "unable to open" in lower or "readonly" in lower:
        return "The file cannot be opened: it may be in use, damaged or not a SQLite database."
    return None


def _count(conn, table: str) -> int:
    return int(conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar() or 0)  # names from COUNTED only


def counts(conn) -> dict:
    """Row counts of the main tables, the active system administrators, and the demo accounts (mock.*)."""
    found = {table: _count(conn, table) for table in COUNTED}
    # An administrator: an active account whose role has the "admin" permission (roles are data, so not by role code).
    found["admins"] = int(conn.execute(text(
        "SELECT COUNT(*) FROM app_user u WHERE u.is_active = 1 AND u.role_code IN (SELECT r.code FROM app_role r "
        "JOIN role_permission p ON p.role_id = r.id WHERE p.permission = 'admin')")).scalar() or 0)
    found["demoAccounts"] = int(conn.execute(text(
        "SELECT COUNT(*) FROM app_user WHERE LOWER(username) LIKE 'mock.%'")).scalar() or 0)
    return found


# ---- the running connection (read-only) ----------------------------------------------------------------------------

def running(settings: Settings, engine: Engine) -> dict:
    """The connection this process uses (from .env), without its password, its health now, and whether it holds the
    demo data."""
    engine_name = "sqlite" if settings.is_sqlite else "oracle"
    if settings.is_sqlite:
        path = sqlite_path(settings)
        try:
            shown = path.resolve().relative_to(PROJECT_ROOT).as_posix()
        except ValueError:
            shown = path.name
        target = {"file": shown}
    else:
        args = settings.oracle_connect_args
        target = {"dsn": args.get("dsn"), "user": args.get("user"), "schema": settings.oracle_schema,
                  "wallet": bool(args.get("wallet_location"))}
    out = {"engine": engine_name, "profile": settings.profile, "source": "ENV", "target": target,
           "expectedVersion": expected_version(engine_name), "schemaVersion": None, "latencyMs": None,
           "health": "FAILED", "error": None, "serverVersion": None, "pool": None, "demoAccounts": None}
    start = time.perf_counter()
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1 FROM dual" if engine_name == "oracle" else "SELECT 1"))
            out["latencyMs"] = _ms(start)
            if engine_name == "sqlite":
                out["schemaVersion"] = conn.execute(text("SELECT MAX(version) FROM SCHEMA_VERSION")).scalar()
            out["demoAccounts"] = int(conn.execute(text(
                "SELECT COUNT(*) FROM app_user WHERE LOWER(username) LIKE 'mock.%'")).scalar() or 0)
            info = conn.dialect.server_version_info
            out["serverVersion"] = ".".join(str(p) for p in info) if info else None
        out["health"] = "HEALTHY"
    except Exception as exc:  # health is a report: any failure is shown, never raised
        out["error"] = _error(exc)
    pool = engine.pool
    if engine_name == "oracle" and hasattr(pool, "size") and hasattr(pool, "checkedout"):
        out["pool"] = {"size": pool.size(), "inUse": pool.checkedout()}
    return out


# ---- the stages ----------------------------------------------------------------------------------------------------

def run_tests(provider: Provider, c: dict, metadata, in_use_key: str) -> list[StageResult]:
    """Run the read-only stages against candidate `c` (candidate()). `in_use_key` (running_key()) says when the
    candidate is the database in use now."""
    results: list[StageResult] = []

    def skip_rest(after: str):
        for stage in STAGES[STAGES.index(after) + 1:]:
            results.append(StageResult(stage, "SKIPPED", "Not run: an earlier stage failed."))
        return results

    oracle = c["engine"] == "oracle"
    where = (f"{c['host']}:{c['port']}/{c['service']} as {c['user']}" if oracle else f"data/{c['name']}")
    same = (candidate_key(provider.id, {"fileName": c.get("name"), "host": c.get("host"), "port": c.get("port"),
                                        "serviceName": c.get("service"), "protocol": c.get("protocol"),
                                        "username": c.get("user"), "schema": c.get("schema")}) == in_use_key)

    # CONNECT
    start = time.perf_counter()
    if oracle:
        try:
            egress.check(c["host"], c["port"], "DATABASE", c["rules"])
        except egress.EgressDenied as exc:
            results.append(StageResult(CONNECT, "FAILED", exc.message, exc.code, _ms(start)))
            return skip_rest(CONNECT)
    elif not c["path"].is_file():
        results.append(StageResult(CONNECT, "FAILED", f"{where} does not exist.", "NOT_FOUND", _ms(start),
                                   "Put the database file in the data folder first (copied while the app is stopped)."))
        return skip_rest(CONNECT)
    engine = _engine(c)
    try:
        try:
            conn = engine.connect()
        except Exception as exc:
            message = _error(exc)
            results.append(StageResult(CONNECT, "FAILED", f"{where}: {message}", "UNREACHABLE", _ms(start),
                                       _hint(message)))
            return skip_rest(CONNECT)
        try:
            return _stages(c, conn, engine, metadata, where, same, start, results, skip_rest)
        finally:
            conn.close()
    finally:
        engine.dispose()


def _stages(c, conn, engine, metadata, where, same, start, results, skip_rest):
    oracle = c["engine"] == "oracle"
    try:
        if oracle:
            row = conn.execute(text(
                "SELECT sys_context('USERENV', 'DB_NAME'), sys_context('USERENV', 'SERVICE_NAME'), "
                "sys_context('USERENV', 'SESSION_USER'), sys_context('USERENV', 'CURRENT_SCHEMA') FROM dual")).one()
            identity = {"database": row[0], "service": row[1], "user": row[2], "schema": row[3]}
            said = f"database {row[0]}, service {row[1]}, signed in as {row[2]}, tables of {row[3]}"
        else:
            conn.execute(text("SELECT 1"))
            identity = {"file": c["name"], "bytes": c["path"].stat().st_size}
            said = f"SQLite {conn.dialect.server_version_info and '.'.join(map(str, conn.dialect.server_version_info))}"
        conn.rollback()
    except Exception as exc:
        message = _error(exc)
        results.append(StageResult(CONNECT, "FAILED", f"{where}: {message}", "QUERY_FAILED", _ms(start), _hint(message)))
        return skip_rest(CONNECT)
    note = " This is the database in use now." if same else ""
    results.append(StageResult(CONNECT, "PASSED", f"Connected to {where} ({said}).{note}", None, _ms(start),
                               detail=identity))

    # SCHEMA
    start = time.perf_counter()
    expected = expected_version(c["engine"])
    if not oracle:
        try:
            have = conn.execute(text("SELECT MAX(version) FROM SCHEMA_VERSION")).scalar()
        except Exception:
            have = None
        conn.rollback()
        if have is None:
            results.append(StageResult(SCHEMA, "FAILED", f"{where} has no schema: it is empty or not this app's "
                                                         f"database.", "NO_SCHEMA", _ms(start)))
            return skip_rest(SCHEMA)
        if int(have) != expected:
            older = int(have) < expected
            results.append(StageResult(SCHEMA, "FAILED", f"{where} has schema version {have}; this app needs "
                                                         f"{expected}.", "SCHEMA_OLD" if older else "SCHEMA_NEWER",
                                       _ms(start), "Start the app once on a copy of it to upgrade it, then test again."
                                       if older else "This database belongs to a newer version of the app."))
            return skip_rest(SCHEMA)
    owner = (c["schema"] or c["user"]) if oracle else None
    try:
        check_schema(engine, metadata, owner)
    except ConfigError as exc:
        problems = str(exc).split(": ", 1)[-1].split("; ")
        shown = "; ".join(problems[:5]) + (f" and {len(problems) - 5} more" if len(problems) > 5 else "")
        empty = all(p.startswith("missing table") for p in problems) and len(problems) >= len(metadata.tables)
        results.append(StageResult(SCHEMA, "FAILED", f"{where}: {shown}.", "NO_SCHEMA" if empty else "SCHEMA_MISMATCH",
                                   _ms(start), f"The DBA applies the db/{c['engine']} scripts V001 to V{expected:03d} "
                                               f"first (docs/oracle-migration.md); Settings never changes a schema."))
        return skip_rest(SCHEMA)
    except Exception as exc:
        results.append(StageResult(SCHEMA, "FAILED", f"{where}: {_error(exc)}", "QUERY_FAILED", _ms(start)))
        return skip_rest(SCHEMA)
    results.append(StageResult(SCHEMA, "PASSED", f"Every table and column of this app is there (version V{expected:03d}).",
                               None, _ms(start)))

    # PERMISSIONS
    start = time.perf_counter()
    if not oracle:
        if not (os.access(c["path"], os.W_OK) and os.access(c["path"].parent, os.W_OK)):
            results.append(StageResult(PERMISSIONS, "FAILED", f"{where} or its folder is read-only for the app.",
                                       "READ_ONLY", _ms(start)))
            return skip_rest(PERMISSIONS)
        results.append(StageResult(PERMISSIONS, "PASSED", f"The app can write {where}.", None, _ms(start)))
    else:
        try:
            for table in sorted(metadata.tables):  # names from the app's own models
                conn.execute(text(f"SELECT 1 FROM {table} WHERE 1 = 0"))
            session_user = conn.execute(text("SELECT sys_context('USERENV', 'SESSION_USER') FROM dual")).scalar()
            rows = conn.execute(text("SELECT table_name, privilege FROM all_tab_privs WHERE table_schema = :owner"),
                                {"owner": owner.upper()}).all()
            conn.rollback()
        except Exception as exc:
            conn.rollback()
            results.append(StageResult(PERMISSIONS, "FAILED", f"{where}: {_error(exc)}", "NO_ACCESS", _ms(start),
                                       "The account cannot read every table: the DBA runs db/oracle/runtime-grants.sql "
                                       "(docs/oracle-migration.md section 3)."))
            return skip_rest(PERMISSIONS)
        if str(session_user).upper() == owner.upper():
            results.append(StageResult(PERMISSIONS, "WARNING", f"{c['user']} owns the tables, so it may do anything "
                                                               f"to them.", "OWNER_ACCOUNT", _ms(start),
                                       "A separate runtime account with only the grants of db/oracle/runtime-grants.sql "
                                       "is safer."))
        else:
            needed = required_grants()
            if needed is None:
                results.append(StageResult(PERMISSIONS, "WARNING", "Every table can be read; the list of grants to "
                                                                   "check is not on this server.", "GRANTS_UNKNOWN",
                                           _ms(start)))
            else:
                have: dict[str, set[str]] = {}
                for name, privilege in rows:
                    have.setdefault(str(name).upper(), set()).add(str(privilege).upper())
                missing = [f"{p} on {obj}" for obj, privileges in sorted(needed.items())
                           for p in sorted(privileges - have.get(obj, set()))]
                if missing:
                    shown = ", ".join(missing[:6]) + (f" and {len(missing) - 6} more" if len(missing) > 6 else "")
                    results.append(StageResult(PERMISSIONS, "FAILED", f"{c['user']} lacks {shown}.", "MISSING_GRANTS",
                                               _ms(start), "The DBA runs db/oracle/runtime-grants.sql "
                                                           "(docs/oracle-migration.md section 3)."))
                    return skip_rest(PERMISSIONS)
                results.append(StageResult(PERMISSIONS, "PASSED", f"{c['user']} has every grant the app needs on "
                                                                  f"{owner}'s tables.", None, _ms(start)))

    # DATA: a clean start (no demo data, ever)
    start = time.perf_counter()
    try:
        found = counts(conn)
        conn.rollback()
    except Exception as exc:
        results.append(StageResult(DATA, "FAILED", f"{where}: {_error(exc)}", "QUERY_FAILED", _ms(start)))
        return results
    summary = (f"{found['app_user']} account(s), {found['admins']} active system administrator(s), "
               f"{found['department']} group(s), {found['capability_model']} model(s), {found['asset']} asset(s), "
               f"{found['project']} project(s)")
    if found["demoAccounts"]:
        results.append(StageResult(DATA, "FAILED", f"{summary}: it holds the demo data ({found['demoAccounts']} demo "
                                                   f"account(s) mock.* and the records they made).", "DEMO_DATA",
                                   _ms(start), "The new database must start clean: use an empty database (the DBA runs "
                                               "the scripts and the grants only); never copy the demo database.",
                                   detail=found))
        return results
    if found["app_user"] == 0:
        results.append(StageResult(DATA, "PASSED", "Empty: a clean start, as intended (no demo data). After the "
                                                   f"restart, `{SETUP_COMMAND}` creates the administrator and the "
                                                   "standard lists.", "EMPTY", _ms(start), detail=found))
        return results
    if found["admins"] == 0:
        results.append(StageResult(DATA, "FAILED", f"{summary}: no active system administrator, so nobody could "
                                                   f"administer the app there.", "NO_ADMIN", _ms(start),
                                   "Create one there first (flask create-user --role SYS_ADMIN), or use an empty "
                                   "database.", detail=found))
        return results
    results.append(StageResult(DATA, "PASSED", f"{summary}; no demo data.", None, _ms(start), detail=found))
    return results
