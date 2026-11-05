"""Oracle test harness (pytest -m oracle tests/oracle -o addopts=). Needs oracle-local.env in the project folder
(ORACLE_DSN, ORACLE_SYSTEM_USER, ORACLE_SYSTEM_PASSWORD; git-ignored) and sqlplus on PATH.

It creates two throwaway accounts with random passwords: CPC_T_OWNER (owns the tables; runs db/oracle/V*.sql with
sqlplus) and CPC_T_APP (the runtime identity, CREATE SESSION plus exactly the grants of docs/oracle-migration.md),
runs the application as CPC_T_APP with ORACLE_SCHEMA=CPC_T_OWNER, and drops both accounts at the end. Nothing else
in the database is touched. Passwords are never printed."""
from __future__ import annotations

import os
import re
import secrets
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parents[3]
OWNER, APP_USER = "CPC_T_OWNER", "CPC_T_APP"


def _env() -> dict:
    from dotenv import dotenv_values
    path = PROJECT / "oracle-local.env"
    if not path.is_file():
        pytest.skip("oracle-local.env not found (local Oracle test database not configured)")
    values = dotenv_values(path)
    if not all(values.get(k) for k in ("ORACLE_DSN", "ORACLE_SYSTEM_USER", "ORACLE_SYSTEM_PASSWORD")):
        pytest.skip("oracle-local.env lacks ORACLE_DSN / ORACLE_SYSTEM_USER / ORACLE_SYSTEM_PASSWORD")
    return values


def _drop(cur, name):
    cur.execute("SELECT COUNT(*) FROM dba_users WHERE username = :n", n=name)
    if cur.fetchone()[0]:
        cur.execute(f"""BEGIN
            FOR s IN (SELECT sid, serial# AS ser FROM v$session WHERE username = '{name}') LOOP
                EXECUTE IMMEDIATE 'ALTER SYSTEM KILL SESSION ''' || s.sid || ',' || s.ser || ''' IMMEDIATE';
            END LOOP;
        END;""")
        cur.execute(f"DROP USER {name} CASCADE")


def _grants() -> list[str]:
    text = (PROJECT / "docs" / "oracle-migration.md").read_text(encoding="utf-8")
    statements = [re.sub(r"\s+--.*$", "", line).rstrip(";").replace("CPC_APP", APP_USER)
                  for line in text.splitlines() if line.startswith("GRANT ") and " ON " in line]
    assert len(statements) >= 40, "the grant list in docs/oracle-migration.md looks incomplete"
    return statements


@pytest.fixture(scope="session")
def oracle_accounts():
    import oracledb

    env = _env()
    sqlplus = shutil.which("sqlplus")
    if not sqlplus:
        pytest.skip("sqlplus is not on PATH")
    owner_pw = "Cpc" + secrets.token_hex(12)
    app_pw = "Cpc" + secrets.token_hex(12)
    system = oracledb.connect(user=env["ORACLE_SYSTEM_USER"], password=env["ORACLE_SYSTEM_PASSWORD"], dsn=env["ORACLE_DSN"])
    cur = system.cursor()
    for name in (APP_USER, OWNER):
        _drop(cur, name)
    cur.execute(f'CREATE USER {OWNER} IDENTIFIED BY "{owner_pw}" QUOTA UNLIMITED ON users')
    cur.execute(f"GRANT CREATE SESSION, CREATE TABLE, CREATE SEQUENCE, CREATE TRIGGER TO {OWNER}")
    cur.execute(f'CREATE USER {APP_USER} IDENTIFIED BY "{app_pw}"')
    cur.execute(f"GRANT CREATE SESSION TO {APP_USER}")
    try:
        # The real DDL scripts, applied the way a DBA would (sqlplus, stop at the first error).
        with tempfile.TemporaryDirectory() as tmp:
            driver = Path(tmp) / "apply.sql"
            scripts = sorted((PROJECT / "db" / "oracle").glob("V*.sql"), key=lambda p: int(p.name[1:4]))
            driver.write_text("WHENEVER SQLERROR EXIT FAILURE\nSET DEFINE OFF\n"
                              + "".join(f"@\"{p}\"\n" for p in scripts) + "EXIT\n", encoding="utf-8")
            result = subprocess.run([sqlplus, "-S", "-L", f"{OWNER}/\"{owner_pw}\"@{env['ORACLE_DSN']}", f"@{driver}"],
                                    capture_output=True, text=True, timeout=600)
            assert result.returncode == 0, "applying db/oracle failed:\n" + result.stdout[-3000:]
        owner = oracledb.connect(user=OWNER, password=owner_pw, dsn=env["ORACLE_DSN"])
        ocur = owner.cursor()
        for statement in _grants():
            ocur.execute(statement)
        ocur.execute(f"""BEGIN
            FOR s IN (SELECT sequence_name FROM user_sequences) LOOP
                EXECUTE IMMEDIATE 'GRANT SELECT ON ' || s.sequence_name || ' TO {APP_USER}';
            END LOOP;
        END;""")
        owner.close()
        yield {"dsn": env["ORACLE_DSN"], "app_password": app_pw, "owner_password": owner_pw}
    finally:
        from app.extensions import db
        try:
            db.dispose()
        except Exception:  # noqa: BLE001 - the pool may never have been created
            pass
        for name in (APP_USER, OWNER):
            _drop(cur, name)
        system.close()


@pytest.fixture(scope="session")
def oracle_app(oracle_accounts, tmp_path_factory):
    from app import create_app
    from app.core.config import load_settings

    os.environ.update({"ORACLE_DSN": oracle_accounts["dsn"], "ORACLE_USER": APP_USER,
                       "ORACLE_PASSWORD": oracle_accounts["app_password"], "ORACLE_SCHEMA": OWNER})
    try:
        settings = load_settings("oracle", {"cookie_secure": False, "log_level": "WARNING", "auth_mode": "local",
                                            "reports_dir": str(tmp_path_factory.mktemp("reports"))})
    finally:
        for key in ("ORACLE_DSN", "ORACLE_USER", "ORACLE_PASSWORD", "ORACLE_SCHEMA"):
            os.environ.pop(key, None)
    app = create_app(settings)  # runs check_schema against the owner's schema
    app.config["TESTING"] = True
    return app
