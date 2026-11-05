-- Custom report templates, scheduled reports and the report run log. The system runs on an isolated network:
-- scheduled reports are written to a folder (never sent by e-mail) and downloaded from the run history. Twin of db/oracle/V006__reports.sql.

CREATE TABLE REPORT_TEMPLATE (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT    NOT NULL CHECK (length(name) BETWEEN 1 AND 120),
    owner_id        INTEGER NOT NULL REFERENCES APP_USER (id),
    is_shared       INTEGER NOT NULL DEFAULT 0 CHECK (is_shared IN (0, 1)),
    definition_json TEXT    NOT NULL CHECK (length(definition_json) BETWEEN 2 AND 4000),
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL,
    created_by      INTEGER NOT NULL REFERENCES APP_USER (id),
    updated_by      INTEGER NOT NULL REFERENCES APP_USER (id),
    version         INTEGER NOT NULL DEFAULT 1,
    archived_at     TEXT,
    archived_by     INTEGER REFERENCES APP_USER (id)
);

CREATE TABLE REPORT_SCHEDULE (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT    NOT NULL CHECK (length(name) BETWEEN 1 AND 120),
    report_key      TEXT    CHECK (report_key IS NULL OR length(report_key) BETWEEN 2 AND 80),
    template_id     INTEGER REFERENCES REPORT_TEMPLATE (id),
    frequency       TEXT    NOT NULL CHECK (frequency IN ('DAILY', 'WEEKLY', 'MONTHLY', 'QUARTERLY')),
    language        TEXT    NOT NULL CHECK (language IN ('EN', 'AR', 'BILINGUAL')),
    file_format     TEXT    NOT NULL CHECK (file_format IN ('XLSX', 'CSV', 'PPTX', 'HTML')),
    run_time        TEXT    NOT NULL CHECK (run_time GLOB '[0-2][0-9]:[0-5][0-9]'),
    -- Sub-folder of the reports output directory (REPORTS_OUTPUT_DIR, local or a shared folder on the local network).
    output_folder   TEXT    NOT NULL CHECK (length(output_folder) BETWEEN 1 AND 80),
    next_run_date   TEXT    NOT NULL CHECK (next_run_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    is_active       INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    owner_id        INTEGER NOT NULL REFERENCES APP_USER (id),
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL,
    created_by      INTEGER NOT NULL REFERENCES APP_USER (id),
    updated_by      INTEGER NOT NULL REFERENCES APP_USER (id),
    version         INTEGER NOT NULL DEFAULT 1,
    CHECK (report_key IS NOT NULL OR template_id IS NOT NULL)
);

-- Every generated report (on screen, exported or scheduled): who, when, what, in which language and format.
CREATE TABLE REPORT_RUN (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    report_key      TEXT    NOT NULL CHECK (length(report_key) BETWEEN 2 AND 80),
    title           TEXT    NOT NULL CHECK (length(title) BETWEEN 1 AND 200),
    schedule_id     INTEGER REFERENCES REPORT_SCHEDULE (id),
    run_at          TEXT    NOT NULL,
    run_by          INTEGER NOT NULL REFERENCES APP_USER (id),
    language        TEXT    NOT NULL CHECK (language IN ('EN', 'AR', 'BILINGUAL')),
    file_format     TEXT    NOT NULL CHECK (file_format IN ('SCREEN', 'XLSX', 'CSV', 'PPTX', 'HTML', 'PRINT')),
    row_count       INTEGER NOT NULL DEFAULT 0 CHECK (row_count >= 0),
    file_name       TEXT    CHECK (file_name IS NULL OR length(file_name) <= 300)
);
CREATE INDEX ix_report_run_at ON REPORT_RUN (run_at);
