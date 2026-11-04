-- Testing & evaluation, maintenance & technical readiness, AI capability, development potential.
-- Twin of db/oracle/V004__testing_maintenance_ai.sql.

CREATE TABLE TEST_EVENT (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    code            TEXT    NOT NULL UNIQUE CHECK (length(code) BETWEEN 2 AND 20 AND code NOT GLOB '*[^-A-Z0-9]*'),
    title_en        TEXT    NOT NULL CHECK (length(title_en) BETWEEN 2 AND 200),
    title_ar        TEXT    NOT NULL CHECK (length(title_ar) BETWEEN 2 AND 200),
    model_id        INTEGER NOT NULL REFERENCES CAPABILITY_MODEL (id),
    asset_id        INTEGER REFERENCES ASSET (id),
    project_id      INTEGER REFERENCES PROJECT (id),
    department_id   INTEGER NOT NULL REFERENCES DEPARTMENT (id),
    site_id         INTEGER REFERENCES SITE (id),
    test_type       TEXT    NOT NULL CHECK (test_type IN ('INTERNAL', 'EXTERNAL')),
    test_date       TEXT    NOT NULL CHECK (test_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    status_code     TEXT    NOT NULL CHECK (length(status_code) BETWEEN 2 AND 30),
    score           INTEGER CHECK (score IS NULL OR score BETWEEN 0 AND 100),
    result_en       TEXT    CHECK (result_en IS NULL OR length(result_en) <= 2000),
    result_ar       TEXT    CHECK (result_ar IS NULL OR length(result_ar) <= 2000),
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL,
    created_by      INTEGER NOT NULL REFERENCES APP_USER (id),
    updated_by      INTEGER NOT NULL REFERENCES APP_USER (id),
    version         INTEGER NOT NULL DEFAULT 1,
    archived_at     TEXT,
    archived_by     INTEGER REFERENCES APP_USER (id)
);
CREATE INDEX ix_test_event_model ON TEST_EVENT (model_id, test_date);
CREATE INDEX ix_test_event_project ON TEST_EVENT (project_id);
CREATE INDEX ix_test_event_department ON TEST_EVENT (department_id);

CREATE TABLE MAINTENANCE_ORDER (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    code                TEXT    NOT NULL UNIQUE CHECK (length(code) BETWEEN 2 AND 20 AND code NOT GLOB '*[^-A-Z0-9]*'),
    asset_id            INTEGER NOT NULL REFERENCES ASSET (id),
    maint_type          TEXT    NOT NULL CHECK (maint_type IN ('PREVENTIVE', 'CORRECTIVE', 'INSPECTION', 'UPGRADE')),
    title_en            TEXT    NOT NULL CHECK (length(title_en) BETWEEN 2 AND 200),
    title_ar            TEXT    NOT NULL CHECK (length(title_ar) BETWEEN 2 AND 200),
    status_code         TEXT    NOT NULL CHECK (length(status_code) BETWEEN 2 AND 30),
    start_date          TEXT    NOT NULL CHECK (start_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    expected_end_date   TEXT    CHECK (expected_end_date IS NULL OR expected_end_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    actual_end_date     TEXT    CHECK (actual_end_date IS NULL OR actual_end_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    progress_pct        INTEGER NOT NULL DEFAULT 0 CHECK (progress_pct BETWEEN 0 AND 100),
    cost                REAL    CHECK (cost IS NULL OR cost >= 0),
    parts_shortage      INTEGER NOT NULL DEFAULT 0 CHECK (parts_shortage IN (0, 1)),
    parts_text          TEXT    CHECK (parts_text IS NULL OR length(parts_text) <= 500),
    performed_by        TEXT    CHECK (performed_by IS NULL OR length(performed_by) <= 160),
    created_at          TEXT    NOT NULL,
    updated_at          TEXT    NOT NULL,
    created_by          INTEGER NOT NULL REFERENCES APP_USER (id),
    updated_by          INTEGER NOT NULL REFERENCES APP_USER (id),
    version             INTEGER NOT NULL DEFAULT 1,
    archived_at         TEXT,
    archived_by         INTEGER REFERENCES APP_USER (id)
);
CREATE INDEX ix_maintenance_order_asset ON MAINTENANCE_ORDER (asset_id, start_date);

CREATE TABLE AI_TECHNOLOGY (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    code            TEXT    NOT NULL UNIQUE CHECK (length(code) BETWEEN 2 AND 30 AND code NOT GLOB '*[^A-Z0-9_]*'),
    name_en         TEXT    NOT NULL CHECK (length(name_en) BETWEEN 1 AND 120),
    name_ar         TEXT    NOT NULL CHECK (length(name_ar) BETWEEN 1 AND 120),
    sort_order      INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL,
    created_by      INTEGER NOT NULL REFERENCES APP_USER (id),
    updated_by      INTEGER NOT NULL REFERENCES APP_USER (id),
    version         INTEGER NOT NULL DEFAULT 1,
    archived_at     TEXT,
    archived_by     INTEGER REFERENCES APP_USER (id)
);

-- A row means: this model supports this AI technology.
CREATE TABLE MODEL_AI_TECH (
    model_id        INTEGER NOT NULL REFERENCES CAPABILITY_MODEL (id),
    technology_id   INTEGER NOT NULL REFERENCES AI_TECHNOLOGY (id),
    created_at      TEXT    NOT NULL,
    PRIMARY KEY (model_id, technology_id)
);
CREATE INDEX ix_model_ai_tech_tech ON MODEL_AI_TECH (technology_id);

-- AI capability levels 1-5: a level is met when the model supports at least `min_supported` technologies and every
-- technology in `required_codes` (comma-separated AI_TECHNOLOGY codes); a model's level is the highest level met
-- together with every lower one. Level 0 = none met.
CREATE TABLE AI_LEVEL_CRITERION (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ai_level        INTEGER NOT NULL UNIQUE CHECK (ai_level BETWEEN 1 AND 5),
    name_en         TEXT    NOT NULL CHECK (length(name_en) BETWEEN 1 AND 120),
    name_ar         TEXT    NOT NULL CHECK (length(name_ar) BETWEEN 1 AND 120),
    description_en  TEXT    CHECK (description_en IS NULL OR length(description_en) <= 500),
    description_ar  TEXT    CHECK (description_ar IS NULL OR length(description_ar) <= 500),
    min_supported   INTEGER NOT NULL DEFAULT 0 CHECK (min_supported BETWEEN 0 AND 100),
    required_codes  TEXT    CHECK (required_codes IS NULL OR length(required_codes) <= 500),
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL,
    created_by      INTEGER NOT NULL REFERENCES APP_USER (id),
    updated_by      INTEGER NOT NULL REFERENCES APP_USER (id),
    version         INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE DEVELOPMENT_OPPORTUNITY (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    code            TEXT    NOT NULL UNIQUE CHECK (length(code) BETWEEN 2 AND 20 AND code NOT GLOB '*[^-A-Z0-9]*'),
    model_id        INTEGER NOT NULL REFERENCES CAPABILITY_MODEL (id),
    dev_type        TEXT    NOT NULL CHECK (dev_type IN ('AI', 'SENSORS', 'ENDURANCE', 'COMMUNICATIONS', 'AUTONOMY',
                        'PAYLOAD', 'SECURITY', 'INTEGRATION', 'OTHER')),
    title_en        TEXT    NOT NULL CHECK (length(title_en) BETWEEN 2 AND 200),
    title_ar        TEXT    NOT NULL CHECK (length(title_ar) BETWEEN 2 AND 200),
    benefit_en      TEXT    CHECK (benefit_en IS NULL OR length(benefit_en) <= 500),
    benefit_ar      TEXT    CHECK (benefit_ar IS NULL OR length(benefit_ar) <= 500),
    status_code     TEXT    NOT NULL CHECK (length(status_code) BETWEEN 2 AND 30),
    complexity      TEXT    NOT NULL CHECK (complexity IN ('LOW', 'MEDIUM', 'HIGH')),
    estimated_cost  REAL    CHECK (estimated_cost IS NULL OR estimated_cost >= 0),
    duration_months INTEGER CHECK (duration_months IS NULL OR duration_months BETWEEN 0 AND 240),
    priority        TEXT    NOT NULL CHECK (priority IN ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW')),
    project_id      INTEGER REFERENCES PROJECT (id),
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL,
    created_by      INTEGER NOT NULL REFERENCES APP_USER (id),
    updated_by      INTEGER NOT NULL REFERENCES APP_USER (id),
    version         INTEGER NOT NULL DEFAULT 1,
    archived_at     TEXT,
    archived_by     INTEGER REFERENCES APP_USER (id)
);
CREATE INDEX ix_development_opportunity_model ON DEVELOPMENT_OPPORTUNITY (model_id);
