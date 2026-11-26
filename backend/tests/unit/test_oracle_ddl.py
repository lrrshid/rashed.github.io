"""The Oracle scripts (db/oracle/V*.sql) create every table and column the application maps, like the SQLite twins.
At start-up on Oracle the app runs check_schema against the live database; this catches a missing twin earlier,
without a database. It also checks that every table has its sequence (where the model uses one) and that the
SQLite and Oracle scripts define the same tables."""
from __future__ import annotations

import re
from pathlib import Path

from app.models import Base

DB = Path(__file__).resolve().parents[3] / "db"
CREATE = re.compile(r"CREATE TABLE (\w+)\s*\((.*?)\n\);", re.S | re.I)
# A column added by a later script: SQLite "ALTER TABLE t ADD COLUMN c ...", Oracle "ALTER TABLE t ADD (c ...)".
ADD_COLUMN = re.compile(r"ALTER TABLE (\w+) ADD (?:COLUMN )?\(?(\w+) ", re.I)
# A SQLite table rebuild (a CHECK constraint widened): CREATE TABLE x_NEW, DROP TABLE x, ALTER TABLE x_NEW RENAME TO x.
DROP = re.compile(r"DROP TABLE (\w+)\s*;", re.I)
RENAME = re.compile(r"ALTER TABLE (\w+) RENAME TO (\w+)", re.I)


def _tables(folder: str) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for path in sorted((DB / folder).glob("V*.sql")):
        for name, body in CREATE.findall(path.read_text(encoding="utf-8")):
            cols = set()
            for line in body.splitlines():
                line = line.strip()
                if not line or line.upper().startswith(("CONSTRAINT", "PRIMARY KEY", "UNIQUE", "CHECK", "--")):
                    continue
                cols.add(line.split()[0].lower())
            out[name.lower()] = cols
        for name, column in ADD_COLUMN.findall(path.read_text(encoding="utf-8")):
            if column.upper() != "CONSTRAINT":
                out.setdefault(name.lower(), set()).add(column.lower())
        for name in DROP.findall(path.read_text(encoding="utf-8")):
            out.pop(name.lower(), None)
        for old, new in RENAME.findall(path.read_text(encoding="utf-8")):
            out[new.lower()] = out.pop(old.lower())
    return out


def test_oracle_scripts_create_every_mapped_column():
    oracle = _tables("oracle")
    problems = []
    for table in Base.metadata.sorted_tables:
        if table.name not in oracle:
            problems.append(f"missing table {table.name}")
            continue
        for column in table.columns:
            if column.name not in oracle[table.name]:
                problems.append(f"{table.name}.{column.name}")
    assert not problems, problems


def test_sqlite_and_oracle_define_the_same_tables():
    sqlite = {k for k in _tables("sqlite")}
    oracle = {k for k in _tables("oracle")}
    assert sqlite == oracle, (sqlite ^ oracle)


def test_every_sequence_used_by_a_model_is_created():
    script = "\n".join(p.read_text(encoding="utf-8") for p in (DB / "oracle").glob("V*.sql")).lower()
    missing = []
    for table in Base.metadata.sorted_tables:
        for column in table.columns:
            seq = getattr(column.default, "name", None) if column.default is not None else None
            if seq and f"create sequence {seq.lower()} " not in script:
                missing.append(seq)
    assert not missing, missing
