-- migrate: foreign-keys-off
-- Golden-sample trials, the reason a capability entered maintenance, and the new kinds of attached scans
-- (trial, higher-level directive letter, official trial form, investigation board, capability deed, live
-- demonstration report, and the culture library: references, user guides, acquisition plans).
-- Twin of db/oracle/V008__golden_samples_attachments.sql.

CREATE TABLE GOLDEN_SAMPLE_TRIAL (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    code            TEXT    NOT NULL UNIQUE CHECK (length(code) BETWEEN 2 AND 20 AND code NOT GLOB '*[^-A-Z0-9]*'),
    title_en        TEXT    NOT NULL CHECK (length(title_en) BETWEEN 2 AND 200),
    title_ar        TEXT    NOT NULL CHECK (length(title_ar) BETWEEN 2 AND 200),
    model_id        INTEGER NOT NULL REFERENCES CAPABILITY_MODEL (id),
    trial_date      TEXT    NOT NULL CHECK (trial_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    status_code     TEXT    NOT NULL CHECK (length(status_code) BETWEEN 2 AND 30),
    notes_en        TEXT    CHECK (notes_en IS NULL OR length(notes_en) <= 2000),
    notes_ar        TEXT    CHECK (notes_ar IS NULL OR length(notes_ar) <= 2000),
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL,
    created_by      INTEGER NOT NULL REFERENCES APP_USER (id),
    updated_by      INTEGER NOT NULL REFERENCES APP_USER (id),
    version         INTEGER NOT NULL DEFAULT 1,
    archived_at     TEXT,
    archived_by     INTEGER REFERENCES APP_USER (id)
);
CREATE INDEX ix_golden_sample_trial_model ON GOLDEN_SAMPLE_TRIAL (model_id, trial_date);

ALTER TABLE MAINTENANCE_ORDER ADD COLUMN entry_reason_en TEXT CHECK (entry_reason_en IS NULL OR length(entry_reason_en) <= 2000);
ALTER TABLE MAINTENANCE_ORDER ADD COLUMN entry_reason_ar TEXT CHECK (entry_reason_ar IS NULL OR length(entry_reason_ar) <= 2000);

-- SQLite cannot change a CHECK constraint in place: DOCUMENT is rebuilt with the wider lists (same columns, same
-- order, same rows; DOCUMENT_VERSION keeps pointing at DOCUMENT by name).
CREATE TABLE DOCUMENT_NEW (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    code            TEXT    NOT NULL UNIQUE CHECK (length(code) BETWEEN 2 AND 20 AND code NOT GLOB '*[^-A-Z0-9]*'),
    title_en        TEXT    NOT NULL CHECK (length(title_en) BETWEEN 2 AND 200),
    title_ar        TEXT    NOT NULL CHECK (length(title_ar) BETWEEN 2 AND 200),
    doc_type        TEXT    NOT NULL CHECK (doc_type IN ('REPORT', 'SPECIFICATION', 'CONTRACT', 'TEST_REPORT', 'MANUAL',
                        'CERTIFICATE', 'CORRESPONDENCE', 'PRESENTATION', 'DATASHEET', 'OTHER',
                        'GOLDEN_TRIAL', 'DIRECTIVE_LETTER', 'OFFICIAL_TRIAL_FORM', 'INVESTIGATION', 'CAPABILITY_DEED',
                        'LIVE_DEMO_REPORT', 'REFERENCE', 'USER_GUIDE', 'ACQUISITION_PLAN')),
    entity_type     TEXT    NOT NULL CHECK (entity_type IN ('CAPABILITY_MODEL', 'ASSET', 'PROJECT', 'TEST_EVENT',
                        'MAINTENANCE_ORDER', 'ORGANIZATION', 'CONTRACT', 'CAPABILITY_REQUIREMENT',
                        'GOLDEN_SAMPLE_TRIAL', 'LIBRARY')),
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
INSERT INTO DOCUMENT_NEW (id, code, title_en, title_ar, doc_type, entity_type, entity_id, department_id, current_version,
                          created_at, updated_at, created_by, updated_by, version, archived_at, archived_by)
    SELECT id, code, title_en, title_ar, doc_type, entity_type, entity_id, department_id, current_version,
           created_at, updated_at, created_by, updated_by, version, archived_at, archived_by FROM DOCUMENT;
DROP TABLE DOCUMENT;
ALTER TABLE DOCUMENT_NEW RENAME TO DOCUMENT;
CREATE INDEX ix_document_entity ON DOCUMENT (entity_type, entity_id);
