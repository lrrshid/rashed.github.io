-- Organisational units that conduct tests: a directorate and its sections (two levels), and the conducting unit of
-- each test. Twin of db/oracle/V007__org_units.sql.

CREATE TABLE ORG_UNIT (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    code            TEXT    NOT NULL UNIQUE CHECK (length(code) BETWEEN 1 AND 20 AND code NOT GLOB '*[^-_A-Z0-9]*'),
    name_en         TEXT    NOT NULL CHECK (length(name_en) BETWEEN 1 AND 200),
    name_ar         TEXT    NOT NULL CHECK (length(name_ar) BETWEEN 1 AND 200),
    parent_id       INTEGER REFERENCES ORG_UNIT (id),
    sort_order      INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL,
    created_by      INTEGER NOT NULL REFERENCES APP_USER (id),
    updated_by      INTEGER NOT NULL REFERENCES APP_USER (id),
    version         INTEGER NOT NULL DEFAULT 1,
    archived_at     TEXT,
    archived_by     INTEGER REFERENCES APP_USER (id),
    CHECK (parent_id IS NULL OR parent_id <> id)
);
CREATE INDEX ix_org_unit_parent ON ORG_UNIT (parent_id);

ALTER TABLE TEST_EVENT ADD COLUMN unit_id INTEGER REFERENCES ORG_UNIT (id);
CREATE INDEX ix_test_event_unit ON TEST_EVENT (unit_id);
