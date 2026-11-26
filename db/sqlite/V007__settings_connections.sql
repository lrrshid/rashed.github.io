-- Settings > connections: the company directory (LDAP) and the main database, managed from the website (ported from
-- the Asset Availability project). Twin of db/oracle/V009__settings_connections.sql. Only adds.
--
-- SETTING_PROFILE      one connection (the directory, a database): its kind, provider, name, whether it is on, and which
--                      revision is active. Deleting archives it.
-- SETTING_REVISION     its numbered versions: the non-secret fields as JSON, the secrets encrypted (AES-256-GCM, key
--                      SETTINGS_KEY, never stored here) and a fingerprint of both; a DRAFT is edited in place.
-- SETTING_TEST         every test stage's outcome, tied to the fingerprint it tested (an edit makes it stale).
-- SETTING_CERT         CA certificates the app trusts for its connections (public data, no private keys).
-- EGRESS_RULE          the destinations the server may connect to (host, port, purpose).
-- CONNECTION_SETTING   the sign-in method and the configuration generation every process watches.
-- PROCESS_HEARTBEAT    which app process runs which generation (rows are pruned).
-- APP_SESSION.reauth_at  when the person last typed their password again (sensitive steps need it within minutes).

ALTER TABLE APP_SESSION ADD COLUMN reauth_at TEXT;

CREATE TABLE SETTING_PROFILE (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    kind                TEXT    NOT NULL CHECK (kind IN ('LDAP', 'SSO', 'DATABASE', 'AI')),
    provider            TEXT    NOT NULL CHECK (length(provider) BETWEEN 2 AND 30),
    name                TEXT    NOT NULL CHECK (length(name) BETWEEN 2 AND 80),
    description         TEXT    CHECK (description IS NULL OR length(description) <= 500),
    purpose             TEXT    NOT NULL CHECK (length(purpose) BETWEEN 2 AND 30),
    enabled             INTEGER NOT NULL DEFAULT 0 CHECK (enabled IN (0, 1)),
    active_revision_id  INTEGER REFERENCES SETTING_REVISION (id),
    created_at          TEXT    NOT NULL,
    updated_at          TEXT    NOT NULL,
    created_by          INTEGER NOT NULL REFERENCES APP_USER (id),
    updated_by          INTEGER NOT NULL REFERENCES APP_USER (id),
    version             INTEGER NOT NULL DEFAULT 1,
    archived_at         TEXT,
    archived_by         INTEGER REFERENCES APP_USER (id),
    CHECK ((archived_at IS NULL) = (archived_by IS NULL))
);
CREATE INDEX ix_setting_profile_kind ON SETTING_PROFILE (kind, purpose);

CREATE TABLE SETTING_REVISION (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id          INTEGER NOT NULL REFERENCES SETTING_PROFILE (id),
    revision_no         INTEGER NOT NULL CHECK (revision_no >= 1),
    state               TEXT    NOT NULL CHECK (state IN ('DRAFT', 'ACTIVE', 'SUPERSEDED', 'DISCARDED')),
    schema_version      INTEGER NOT NULL CHECK (schema_version >= 1),
    fields_json         TEXT    NOT NULL,
    secrets_json        TEXT,
    fingerprint         TEXT    NOT NULL CHECK (length(fingerprint) = 64),
    note                TEXT    CHECK (note IS NULL OR length(note) <= 500),
    created_at          TEXT    NOT NULL,
    updated_at          TEXT    NOT NULL,
    created_by          INTEGER NOT NULL REFERENCES APP_USER (id),
    updated_by          INTEGER NOT NULL REFERENCES APP_USER (id),
    version             INTEGER NOT NULL DEFAULT 1,
    UNIQUE (profile_id, revision_no)
);

CREATE TABLE SETTING_TEST (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id          INTEGER NOT NULL REFERENCES SETTING_PROFILE (id),
    revision_id         INTEGER REFERENCES SETTING_REVISION (id),
    fingerprint         TEXT    NOT NULL CHECK (length(fingerprint) = 64),
    stage               TEXT    NOT NULL CHECK (length(stage) BETWEEN 2 AND 30),
    outcome             TEXT    NOT NULL CHECK (outcome IN ('PASSED', 'WARNING', 'FAILED', 'SKIPPED')),
    code                TEXT    CHECK (code IS NULL OR length(code) <= 40),
    message             TEXT    CHECK (message IS NULL OR length(message) <= 500),
    latency_ms          INTEGER CHECK (latency_ms IS NULL OR latency_ms >= 0),
    tested_at           TEXT    NOT NULL,
    tested_by           INTEGER NOT NULL REFERENCES APP_USER (id)
);
CREATE INDEX ix_setting_test_profile ON SETTING_TEST (profile_id, tested_at);

CREATE TABLE SETTING_CERT (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    name                TEXT    NOT NULL CHECK (length(name) BETWEEN 2 AND 80),
    pem                 TEXT    NOT NULL,
    sha256              TEXT    NOT NULL UNIQUE CHECK (length(sha256) = 64),
    subject             TEXT    NOT NULL CHECK (length(subject) <= 500),
    issuer              TEXT    NOT NULL CHECK (length(issuer) <= 500),
    not_before          TEXT    NOT NULL,
    not_after           TEXT    NOT NULL,
    created_at          TEXT    NOT NULL,
    updated_at          TEXT    NOT NULL,
    created_by          INTEGER NOT NULL REFERENCES APP_USER (id),
    updated_by          INTEGER NOT NULL REFERENCES APP_USER (id),
    version             INTEGER NOT NULL DEFAULT 1,
    archived_at         TEXT,
    archived_by         INTEGER REFERENCES APP_USER (id),
    CHECK ((archived_at IS NULL) = (archived_by IS NULL))
);

CREATE TABLE EGRESS_RULE (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    host                TEXT    NOT NULL CHECK (length(host) BETWEEN 1 AND 253),
    port                INTEGER NOT NULL CHECK (port BETWEEN 1 AND 65535),
    purpose             TEXT    NOT NULL CHECK (purpose IN ('LDAP', 'SSO', 'DATABASE', 'AI')),
    note                TEXT    CHECK (note IS NULL OR length(note) <= 500),
    created_at          TEXT    NOT NULL,
    updated_at          TEXT    NOT NULL,
    created_by          INTEGER NOT NULL REFERENCES APP_USER (id),
    updated_by          INTEGER NOT NULL REFERENCES APP_USER (id),
    version             INTEGER NOT NULL DEFAULT 1,
    archived_at         TEXT,
    archived_by         INTEGER REFERENCES APP_USER (id),
    CHECK ((archived_at IS NULL) = (archived_by IS NULL))
);

CREATE TABLE CONNECTION_SETTING (
    name                TEXT    PRIMARY KEY CHECK (length(name) BETWEEN 2 AND 40),
    value               TEXT    NOT NULL CHECK (length(value) <= 500),
    updated_at          TEXT    NOT NULL,
    updated_by          INTEGER REFERENCES APP_USER (id),
    version             INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE PROCESS_HEARTBEAT (
    id                  TEXT    PRIMARY KEY CHECK (length(id) BETWEEN 1 AND 120),
    generation          INTEGER NOT NULL CHECK (generation >= 0),
    started_at          TEXT    NOT NULL,
    last_seen_at        TEXT    NOT NULL
);
