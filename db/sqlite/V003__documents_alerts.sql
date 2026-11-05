-- Versioned documents, alert routing rules and acknowledgements.
-- Twin of db/oracle/V005__documents_alerts.sql.

CREATE TABLE DOCUMENT (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    code            TEXT    NOT NULL UNIQUE CHECK (length(code) BETWEEN 2 AND 20 AND code NOT GLOB '*[^-A-Z0-9]*'),
    title_en        TEXT    NOT NULL CHECK (length(title_en) BETWEEN 2 AND 200),
    title_ar        TEXT    NOT NULL CHECK (length(title_ar) BETWEEN 2 AND 200),
    doc_type        TEXT    NOT NULL CHECK (doc_type IN ('REPORT', 'SPECIFICATION', 'CONTRACT', 'TEST_REPORT', 'MANUAL',
                        'CERTIFICATE', 'CORRESPONDENCE', 'PRESENTATION', 'DATASHEET', 'OTHER')),
    entity_type     TEXT    NOT NULL CHECK (entity_type IN ('CAPABILITY_MODEL', 'ASSET', 'PROJECT', 'TEST_EVENT',
                        'MAINTENANCE_ORDER', 'ORGANIZATION', 'CONTRACT', 'CAPABILITY_REQUIREMENT')),
    entity_id       INTEGER NOT NULL,
    department_id   INTEGER REFERENCES DEPARTMENT (id),
    current_version INTEGER NOT NULL DEFAULT 0 CHECK (current_version >= 0),
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL,
    created_by      INTEGER NOT NULL REFERENCES APP_USER (id),
    updated_by      INTEGER NOT NULL REFERENCES APP_USER (id),
    version         INTEGER NOT NULL DEFAULT 1,
    archived_at     TEXT,
    archived_by     INTEGER REFERENCES APP_USER (id)
);
CREATE INDEX ix_document_entity ON DOCUMENT (entity_type, entity_id);

-- Every uploaded file is a new version; versions are never changed or deleted. Files are kept on disk under
-- data/files/<sha256> (the same bytes are stored once).
CREATE TABLE DOCUMENT_VERSION (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id     INTEGER NOT NULL REFERENCES DOCUMENT (id),
    version_no      INTEGER NOT NULL CHECK (version_no >= 1),
    file_name       TEXT    NOT NULL CHECK (length(file_name) BETWEEN 1 AND 200),
    content_type    TEXT    NOT NULL CHECK (length(content_type) BETWEEN 3 AND 120),
    size_bytes      INTEGER NOT NULL CHECK (size_bytes BETWEEN 1 AND 52428800),
    sha256          TEXT    NOT NULL CHECK (length(sha256) = 64),
    note            TEXT    CHECK (note IS NULL OR length(note) <= 500),
    uploaded_at     TEXT    NOT NULL,
    uploaded_by     INTEGER NOT NULL REFERENCES APP_USER (id),
    UNIQUE (document_id, version_no)
);
CREATE TRIGGER trg_document_version_no_update BEFORE UPDATE ON DOCUMENT_VERSION
BEGIN
    SELECT RAISE(ABORT, 'DOCUMENT_VERSION is append-only');
END;
CREATE TRIGGER trg_document_version_no_delete BEFORE DELETE ON DOCUMENT_VERSION
BEGIN
    SELECT RAISE(ABORT, 'DOCUMENT_VERSION is append-only');
END;

-- Which roles see each alert type, and its look-ahead in days where it has one.
CREATE TABLE ALERT_RULE (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_type      TEXT    NOT NULL UNIQUE CHECK (length(alert_type) BETWEEN 2 AND 40 AND alert_type NOT GLOB '*[^A-Z_]*'),
    role_codes      TEXT    NOT NULL CHECK (length(role_codes) <= 500),
    is_enabled      INTEGER NOT NULL DEFAULT 1 CHECK (is_enabled IN (0, 1)),
    days_ahead      INTEGER CHECK (days_ahead IS NULL OR days_ahead BETWEEN 0 AND 3650),
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL,
    created_by      INTEGER NOT NULL REFERENCES APP_USER (id),
    updated_by      INTEGER NOT NULL REFERENCES APP_USER (id),
    version         INTEGER NOT NULL DEFAULT 1
);

-- Alerts are computed from the records; a user's acknowledgement is kept by the alert's stable key.
CREATE TABLE ALERT_ACK (
    alert_key       TEXT    NOT NULL CHECK (length(alert_key) BETWEEN 3 AND 120),
    user_id         INTEGER NOT NULL REFERENCES APP_USER (id),
    acked_at        TEXT    NOT NULL,
    PRIMARY KEY (alert_key, user_id)
);
