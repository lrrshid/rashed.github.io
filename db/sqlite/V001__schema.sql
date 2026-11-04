-- Capability Portfolio Command: SQLite schema V001 (demo and test profiles).
-- Twin of db/oracle/V001__schema.sql + V002__indexes.sql + V003__audit_append_only.sql.
-- Conventions (inherited from ship-project): singular table names; INTEGER PRIMARY KEY AUTOINCREMENT ids; instants as
-- naive UTC ISO text; calendar dates as YYYY-MM-DD text; booleans 0/1; every enum and length checked here as on
-- Oracle; business tables carry created/updated at/by and an optimistic-lock version; records are archived, never
-- deleted; AUDIT_EVENT is append-only.

-- ---------------------------------------------------------------- security ----------------------------------------
CREATE TABLE APP_ROLE (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    code            TEXT    NOT NULL UNIQUE CHECK (length(code) BETWEEN 2 AND 30 AND code NOT GLOB '*[^A-Z0-9_]*'),
    name_en         TEXT    NOT NULL CHECK (length(name_en) BETWEEN 2 AND 120),
    name_ar         TEXT    NOT NULL CHECK (length(name_ar) BETWEEN 2 AND 120),
    scope           TEXT    NOT NULL DEFAULT 'ALL' CHECK (scope IN ('ALL', 'DEPARTMENT')),
    is_system       INTEGER NOT NULL DEFAULT 0 CHECK (is_system IN (0, 1)),
    sort_order      INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL,
    version         INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE APP_USER (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    username        TEXT    NOT NULL UNIQUE CHECK (length(username) BETWEEN 2 AND 120),
    display_name    TEXT    NOT NULL CHECK (length(display_name) BETWEEN 1 AND 160),
    password_hash   TEXT    NOT NULL CHECK (length(password_hash) BETWEEN 1 AND 255),
    role_code       TEXT    NOT NULL REFERENCES APP_ROLE (code),
    is_active       INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL,
    version         INTEGER NOT NULL DEFAULT 1
);
CREATE UNIQUE INDEX uq_app_user_username_ci ON APP_USER (username COLLATE NOCASE);

CREATE TABLE ROLE_PERMISSION (
    role_id         INTEGER NOT NULL REFERENCES APP_ROLE (id),
    permission      TEXT    NOT NULL CHECK (permission IN ('view', 'edit.requirements', 'edit.models', 'edit.assets',
                        'edit.projects', 'edit.risks', 'edit.maintenance', 'edit.testing', 'edit.documents',
                        'reports.view', 'reports.exec', 'reports.build', 'reports.schedule', 'export', 'admin')),
    created_at      TEXT    NOT NULL,
    PRIMARY KEY (role_id, permission)
);

CREATE TABLE APP_SESSION (
    id              TEXT    PRIMARY KEY CHECK (length(id) = 64),
    user_id         INTEGER NOT NULL REFERENCES APP_USER (id),
    csrf_token      TEXT    NOT NULL CHECK (length(csrf_token) = 64),
    created_at      TEXT    NOT NULL,
    last_seen_at    TEXT    NOT NULL
);
CREATE INDEX ix_app_session_user ON APP_SESSION (user_id);

CREATE TABLE AUDIT_EVENT (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id        INTEGER NOT NULL REFERENCES APP_USER (id),
    action          TEXT    NOT NULL CHECK (length(action) BETWEEN 1 AND 40),
    entity_type     TEXT    NOT NULL CHECK (length(entity_type) BETWEEN 2 AND 30 AND entity_type NOT GLOB '*[^A-Z_]*'),
    entity_id       INTEGER NOT NULL,
    occurred_at     TEXT    NOT NULL,
    before_json     TEXT,
    after_json      TEXT,
    reason          TEXT    CHECK (reason IS NULL OR length(reason) <= 2000)
);
CREATE INDEX ix_audit_event_entity ON AUDIT_EVENT (entity_type, entity_id);
CREATE INDEX ix_audit_event_occurred ON AUDIT_EVENT (occurred_at);
CREATE INDEX ix_audit_event_actor ON AUDIT_EVENT (actor_id);

-- Audit rows are append-only: the database refuses updates and deletes.
CREATE TRIGGER trg_audit_event_no_update BEFORE UPDATE ON AUDIT_EVENT
BEGIN
    SELECT RAISE(ABORT, 'AUDIT_EVENT is append-only');
END;
CREATE TRIGGER trg_audit_event_no_delete BEFORE DELETE ON AUDIT_EVENT
BEGIN
    SELECT RAISE(ABORT, 'AUDIT_EVENT is append-only');
END;

-- Business rules (what counts as available, forecast statuses, thresholds, readiness weights): one JSON value per key.
CREATE TABLE APP_SETTING (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    setting_key     TEXT    NOT NULL UNIQUE CHECK (length(setting_key) BETWEEN 2 AND 60 AND setting_key NOT GLOB '*[^a-z0-9_.]*'),
    value_json      TEXT    NOT NULL CHECK (length(value_json) BETWEEN 1 AND 4000),
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL,
    created_by      INTEGER NOT NULL REFERENCES APP_USER (id),
    updated_by      INTEGER NOT NULL REFERENCES APP_USER (id),
    version         INTEGER NOT NULL DEFAULT 1
);

-- A user's saved filter set on a list page (registry, projects, ...). Personal, not business data: not audited.
CREATE TABLE SAVED_VIEW (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES APP_USER (id),
    page            TEXT    NOT NULL CHECK (length(page) BETWEEN 2 AND 40),
    name            TEXT    NOT NULL CHECK (length(name) BETWEEN 1 AND 80),
    filters_json    TEXT    NOT NULL CHECK (length(filters_json) BETWEEN 2 AND 4000),
    created_at      TEXT    NOT NULL
);
CREATE INDEX ix_saved_view_user ON SAVED_VIEW (user_id, page);

-- ---------------------------------------------------------------- configurable lists ------------------------------
CREATE TABLE DEPARTMENT (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    code            TEXT    NOT NULL UNIQUE CHECK (length(code) BETWEEN 1 AND 20 AND code NOT GLOB '*[^-A-Z0-9]*'),
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

CREATE TABLE USER_DEPARTMENT (
    user_id         INTEGER NOT NULL REFERENCES APP_USER (id),
    department_id   INTEGER NOT NULL REFERENCES DEPARTMENT (id),
    created_at      TEXT    NOT NULL,
    PRIMARY KEY (user_id, department_id)
);

CREATE TABLE CAPABILITY_CATEGORY (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    code            TEXT    NOT NULL UNIQUE CHECK (length(code) BETWEEN 1 AND 20 AND code NOT GLOB '*[^-A-Z0-9]*'),
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

CREATE TABLE SITE (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    code            TEXT    NOT NULL UNIQUE CHECK (length(code) BETWEEN 1 AND 20 AND code NOT GLOB '*[^-A-Z0-9]*'),
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

-- Manufacturers and suppliers.
CREATE TABLE ORGANIZATION (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    code            TEXT    NOT NULL UNIQUE CHECK (length(code) BETWEEN 1 AND 20 AND code NOT GLOB '*[^-A-Z0-9]*'),
    name_en         TEXT    NOT NULL CHECK (length(name_en) BETWEEN 1 AND 160),
    name_ar         TEXT    NOT NULL CHECK (length(name_ar) BETWEEN 1 AND 160),
    kind            TEXT    NOT NULL CHECK (kind IN ('MANUFACTURER', 'SUPPLIER', 'BOTH')),
    country_en      TEXT    CHECK (country_en IS NULL OR length(country_en) <= 80),
    country_ar      TEXT    CHECK (country_ar IS NULL OR length(country_ar) <= 80),
    sort_order      INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL,
    created_by      INTEGER NOT NULL REFERENCES APP_USER (id),
    updated_by      INTEGER NOT NULL REFERENCES APP_USER (id),
    version         INTEGER NOT NULL DEFAULT 1,
    archived_at     TEXT,
    archived_by     INTEGER REFERENCES APP_USER (id)
);

-- The status lists of every record type, configurable without code. `status_domain` names the record type.
CREATE TABLE STATUS_DEF (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    status_domain   TEXT    NOT NULL CHECK (status_domain IN ('ASSET', 'PROJECT', 'MILESTONE', 'RISK', 'ISSUE', 'TEST',
                        'MAINTENANCE', 'DEVELOPMENT')),
    code            TEXT    NOT NULL CHECK (length(code) BETWEEN 2 AND 30 AND code NOT GLOB '*[^A-Z0-9_]*'),
    name_en         TEXT    NOT NULL CHECK (length(name_en) BETWEEN 1 AND 120),
    name_ar         TEXT    NOT NULL CHECK (length(name_ar) BETWEEN 1 AND 120),
    color           TEXT    NOT NULL DEFAULT 'grey' CHECK (color IN ('green', 'amber', 'red', 'blue', 'purple', 'teal',
                        'grey', 'orange', 'pink', 'dark')),
    is_terminal     INTEGER NOT NULL DEFAULT 0 CHECK (is_terminal IN (0, 1)),
    sort_order      INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL,
    created_by      INTEGER NOT NULL REFERENCES APP_USER (id),
    updated_by      INTEGER NOT NULL REFERENCES APP_USER (id),
    version         INTEGER NOT NULL DEFAULT 1,
    archived_at     TEXT,
    archived_by     INTEGER REFERENCES APP_USER (id),
    UNIQUE (status_domain, code)
);

CREATE TABLE PROJECT_TYPE (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    code            TEXT    NOT NULL UNIQUE CHECK (length(code) BETWEEN 2 AND 30 AND code NOT GLOB '*[^A-Z0-9_]*'),
    name_en         TEXT    NOT NULL CHECK (length(name_en) BETWEEN 1 AND 120),
    name_ar         TEXT    NOT NULL CHECK (length(name_ar) BETWEEN 1 AND 120),
    color           TEXT    NOT NULL DEFAULT 'blue' CHECK (color IN ('green', 'amber', 'red', 'blue', 'purple', 'teal',
                        'grey', 'orange', 'pink', 'dark')),
    sort_order      INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL,
    created_by      INTEGER NOT NULL REFERENCES APP_USER (id),
    updated_by      INTEGER NOT NULL REFERENCES APP_USER (id),
    version         INTEGER NOT NULL DEFAULT 1,
    archived_at     TEXT,
    archived_by     INTEGER REFERENCES APP_USER (id)
);

-- The ordered workflow stages of each project type.
CREATE TABLE WORKFLOW_STAGE (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_type_id INTEGER NOT NULL REFERENCES PROJECT_TYPE (id),
    name_en         TEXT    NOT NULL CHECK (length(name_en) BETWEEN 1 AND 120),
    name_ar         TEXT    NOT NULL CHECK (length(name_ar) BETWEEN 1 AND 120),
    sort_order      INTEGER NOT NULL,
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL,
    created_by      INTEGER NOT NULL REFERENCES APP_USER (id),
    updated_by      INTEGER NOT NULL REFERENCES APP_USER (id),
    version         INTEGER NOT NULL DEFAULT 1,
    archived_at     TEXT,
    archived_by     INTEGER REFERENCES APP_USER (id)
);
CREATE INDEX ix_workflow_stage_type ON WORKFLOW_STAGE (project_type_id, sort_order);

-- Technical specification fields per category (performance, sensors, communications, environment, ...).
CREATE TABLE SPEC_FIELD (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id     INTEGER NOT NULL REFERENCES CAPABILITY_CATEGORY (id),
    section         TEXT    NOT NULL CHECK (section IN ('PERFORMANCE', 'SENSORS', 'COMMUNICATIONS', 'ENVIRONMENT', 'OTHER')),
    code            TEXT    NOT NULL CHECK (length(code) BETWEEN 2 AND 40 AND code NOT GLOB '*[^a-z0-9_]*'),
    name_en         TEXT    NOT NULL CHECK (length(name_en) BETWEEN 1 AND 120),
    name_ar         TEXT    NOT NULL CHECK (length(name_ar) BETWEEN 1 AND 120),
    unit            TEXT    CHECK (unit IS NULL OR length(unit) <= 20),
    data_type       TEXT    NOT NULL CHECK (data_type IN ('TEXT', 'NUMBER', 'BOOL')),
    is_custom       INTEGER NOT NULL DEFAULT 0 CHECK (is_custom IN (0, 1)),
    sort_order      INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL,
    created_by      INTEGER NOT NULL REFERENCES APP_USER (id),
    updated_by      INTEGER NOT NULL REFERENCES APP_USER (id),
    version         INTEGER NOT NULL DEFAULT 1,
    archived_at     TEXT,
    archived_by     INTEGER REFERENCES APP_USER (id),
    UNIQUE (category_id, code)
);

-- ---------------------------------------------------------------- capability records ------------------------------
CREATE TABLE CAPABILITY_REQUIREMENT (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    code            TEXT    NOT NULL UNIQUE CHECK (length(code) BETWEEN 2 AND 20 AND code NOT GLOB '*[^-A-Z0-9]*'),
    name_en         TEXT    NOT NULL CHECK (length(name_en) BETWEEN 2 AND 200),
    name_ar         TEXT    NOT NULL CHECK (length(name_ar) BETWEEN 2 AND 200),
    department_id   INTEGER NOT NULL REFERENCES DEPARTMENT (id),
    category_id     INTEGER NOT NULL REFERENCES CAPABILITY_CATEGORY (id),
    required_qty    INTEGER NOT NULL CHECK (required_qty BETWEEN 0 AND 100000),
    priority        TEXT    NOT NULL CHECK (priority IN ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW')),
    target_date     TEXT    CHECK (target_date IS NULL OR target_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    notes           TEXT    CHECK (notes IS NULL OR length(notes) <= 4000),
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL,
    created_by      INTEGER NOT NULL REFERENCES APP_USER (id),
    updated_by      INTEGER NOT NULL REFERENCES APP_USER (id),
    version         INTEGER NOT NULL DEFAULT 1,
    archived_at     TEXT,
    archived_by     INTEGER REFERENCES APP_USER (id)
);
CREATE INDEX ix_requirement_dept_cat ON CAPABILITY_REQUIREMENT (department_id, category_id);

-- A platform or system type (Falcon-X, Q4, ...).
CREATE TABLE CAPABILITY_MODEL (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    code            TEXT    NOT NULL UNIQUE CHECK (length(code) BETWEEN 2 AND 20 AND code NOT GLOB '*[^-A-Z0-9]*'),
    name_en         TEXT    NOT NULL CHECK (length(name_en) BETWEEN 1 AND 160),
    name_ar         TEXT    NOT NULL CHECK (length(name_ar) BETWEEN 1 AND 160),
    category_id     INTEGER NOT NULL REFERENCES CAPABILITY_CATEGORY (id),
    manufacturer_id INTEGER REFERENCES ORGANIZATION (id),
    role_en         TEXT    CHECK (role_en IS NULL OR length(role_en) <= 200),
    role_ar         TEXT    CHECK (role_ar IS NULL OR length(role_ar) <= 200),
    unit_cost       REAL    CHECK (unit_cost IS NULL OR unit_cost >= 0),
    specs_json      TEXT    CHECK (specs_json IS NULL OR length(specs_json) <= 4000),
    notes           TEXT    CHECK (notes IS NULL OR length(notes) <= 4000),
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL,
    created_by      INTEGER NOT NULL REFERENCES APP_USER (id),
    updated_by      INTEGER NOT NULL REFERENCES APP_USER (id),
    version         INTEGER NOT NULL DEFAULT 1,
    archived_at     TEXT,
    archived_by     INTEGER REFERENCES APP_USER (id)
);
CREATE INDEX ix_model_category ON CAPABILITY_MODEL (category_id);

-- Which models fulfil a requirement (its assets count toward the requirement in the requirement's department).
CREATE TABLE REQUIREMENT_MODEL (
    requirement_id  INTEGER NOT NULL REFERENCES CAPABILITY_REQUIREMENT (id),
    model_id        INTEGER NOT NULL REFERENCES CAPABILITY_MODEL (id),
    created_at      TEXT    NOT NULL,
    PRIMARY KEY (requirement_id, model_id)
);
CREATE INDEX ix_requirement_model_model ON REQUIREMENT_MODEL (model_id);

CREATE TABLE CONTRACT (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    code            TEXT    NOT NULL UNIQUE CHECK (length(code) BETWEEN 2 AND 30 AND code NOT GLOB '*[^-A-Z0-9]*'),
    title_en        TEXT    NOT NULL CHECK (length(title_en) BETWEEN 1 AND 200),
    title_ar        TEXT    NOT NULL CHECK (length(title_ar) BETWEEN 1 AND 200),
    supplier_id     INTEGER REFERENCES ORGANIZATION (id),
    contract_value  REAL    CHECK (contract_value IS NULL OR contract_value >= 0),
    start_date      TEXT    CHECK (start_date IS NULL OR start_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    end_date        TEXT    CHECK (end_date IS NULL OR end_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL,
    created_by      INTEGER NOT NULL REFERENCES APP_USER (id),
    updated_by      INTEGER NOT NULL REFERENCES APP_USER (id),
    version         INTEGER NOT NULL DEFAULT 1,
    archived_at     TEXT,
    archived_by     INTEGER REFERENCES APP_USER (id)
);

-- Each physical unit.
CREATE TABLE ASSET (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    code                    TEXT    NOT NULL UNIQUE CHECK (length(code) BETWEEN 2 AND 30 AND code NOT GLOB '*[^-A-Z0-9]*'),
    serial_number           TEXT    CHECK (serial_number IS NULL OR length(serial_number) BETWEEN 1 AND 60),
    model_id                INTEGER NOT NULL REFERENCES CAPABILITY_MODEL (id),
    department_id           INTEGER NOT NULL REFERENCES DEPARTMENT (id),
    site_id                 INTEGER REFERENCES SITE (id),
    status_code             TEXT    NOT NULL CHECK (length(status_code) BETWEEN 2 AND 30),
    readiness_operational   INTEGER CHECK (readiness_operational IS NULL OR readiness_operational BETWEEN 0 AND 100),
    readiness_technical     INTEGER CHECK (readiness_technical IS NULL OR readiness_technical BETWEEN 0 AND 100),
    readiness_mission       INTEGER CHECK (readiness_mission IS NULL OR readiness_mission BETWEEN 0 AND 100),
    readiness_maintenance   INTEGER CHECK (readiness_maintenance IS NULL OR readiness_maintenance BETWEEN 0 AND 100),
    acquisition_date        TEXT    CHECK (acquisition_date IS NULL OR acquisition_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    expected_delivery_date  TEXT    CHECK (expected_delivery_date IS NULL OR expected_delivery_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    acquisition_method      TEXT    CHECK (acquisition_method IS NULL OR acquisition_method IN ('DIRECT_CONTRACT', 'TENDER',
                                'GOVERNMENT', 'DONATION', 'DEVELOPMENT', 'OTHER')),
    contract_id             INTEGER REFERENCES CONTRACT (id),
    warranty_end_date       TEXT    CHECK (warranty_end_date IS NULL OR warranty_end_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    unit_value              REAL    CHECK (unit_value IS NULL OR unit_value >= 0),
    service_life_years      INTEGER CHECK (service_life_years IS NULL OR service_life_years BETWEEN 0 AND 100),
    operating_hours         INTEGER CHECK (operating_hours IS NULL OR operating_hours >= 0),
    responsible_en          TEXT    CHECK (responsible_en IS NULL OR length(responsible_en) <= 160),
    responsible_ar          TEXT    CHECK (responsible_ar IS NULL OR length(responsible_ar) <= 160),
    notes                   TEXT    CHECK (notes IS NULL OR length(notes) <= 4000),
    created_at              TEXT    NOT NULL,
    updated_at              TEXT    NOT NULL,
    created_by              INTEGER NOT NULL REFERENCES APP_USER (id),
    updated_by              INTEGER NOT NULL REFERENCES APP_USER (id),
    version                 INTEGER NOT NULL DEFAULT 1,
    archived_at             TEXT,
    archived_by             INTEGER REFERENCES APP_USER (id)
);
CREATE INDEX ix_asset_model ON ASSET (model_id);
CREATE INDEX ix_asset_department ON ASSET (department_id, status_code);
CREATE INDEX ix_asset_site ON ASSET (site_id);
CREATE UNIQUE INDEX uq_asset_serial ON ASSET (serial_number) WHERE serial_number IS NOT NULL;

-- Status and readiness history (feeds trend reports). Written with every status or readiness change.
CREATE TABLE ASSET_STATUS_HISTORY (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id        INTEGER NOT NULL REFERENCES ASSET (id),
    status_code     TEXT    NOT NULL CHECK (length(status_code) BETWEEN 2 AND 30),
    readiness       INTEGER CHECK (readiness IS NULL OR readiness BETWEEN 0 AND 100),
    changed_at      TEXT    NOT NULL,
    changed_by      INTEGER NOT NULL REFERENCES APP_USER (id),
    note            TEXT    CHECK (note IS NULL OR length(note) <= 2000)
);
CREATE INDEX ix_asset_status_history_asset ON ASSET_STATUS_HISTORY (asset_id, changed_at);

-- ---------------------------------------------------------------- projects ----------------------------------------
CREATE TABLE PROJECT (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    code                TEXT    NOT NULL UNIQUE CHECK (length(code) BETWEEN 2 AND 20 AND code NOT GLOB '*[^-A-Z0-9]*'),
    name_en             TEXT    NOT NULL CHECK (length(name_en) BETWEEN 2 AND 200),
    name_ar             TEXT    NOT NULL CHECK (length(name_ar) BETWEEN 2 AND 200),
    project_type_id     INTEGER NOT NULL REFERENCES PROJECT_TYPE (id),
    department_id       INTEGER NOT NULL REFERENCES DEPARTMENT (id),
    category_id         INTEGER NOT NULL REFERENCES CAPABILITY_CATEGORY (id),
    status_code         TEXT    NOT NULL CHECK (length(status_code) BETWEEN 2 AND 30),
    stage_id            INTEGER REFERENCES WORKFLOW_STAGE (id),
    manager_name        TEXT    CHECK (manager_name IS NULL OR length(manager_name) <= 160),
    supplier_id         INTEGER REFERENCES ORGANIZATION (id),
    contract_id         INTEGER REFERENCES CONTRACT (id),
    budget              REAL    CHECK (budget IS NULL OR budget >= 0),
    committed           REAL    CHECK (committed IS NULL OR committed >= 0),
    actual_spend        REAL    CHECK (actual_spend IS NULL OR actual_spend >= 0),
    progress_pct        INTEGER NOT NULL DEFAULT 0 CHECK (progress_pct BETWEEN 0 AND 100),
    start_date          TEXT    CHECK (start_date IS NULL OR start_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    baseline_end_date   TEXT    CHECK (baseline_end_date IS NULL OR baseline_end_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    target_end_date     TEXT    CHECK (target_end_date IS NULL OR target_end_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    forecast_end_date   TEXT    CHECK (forecast_end_date IS NULL OR forecast_end_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    actual_end_date     TEXT    CHECK (actual_end_date IS NULL OR actual_end_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    next_action_en      TEXT    CHECK (next_action_en IS NULL OR length(next_action_en) <= 2000),
    next_action_ar      TEXT    CHECK (next_action_ar IS NULL OR length(next_action_ar) <= 2000),
    notes_en            TEXT    CHECK (notes_en IS NULL OR length(notes_en) <= 4000),
    notes_ar            TEXT    CHECK (notes_ar IS NULL OR length(notes_ar) <= 4000),
    created_at          TEXT    NOT NULL,
    updated_at          TEXT    NOT NULL,
    created_by          INTEGER NOT NULL REFERENCES APP_USER (id),
    updated_by          INTEGER NOT NULL REFERENCES APP_USER (id),
    version             INTEGER NOT NULL DEFAULT 1,
    archived_at         TEXT,
    archived_by         INTEGER REFERENCES APP_USER (id)
);
CREATE INDEX ix_project_department ON PROJECT (department_id, status_code);
CREATE INDEX ix_project_type ON PROJECT (project_type_id);

-- The quantity a project delivers toward a requirement (counted in the forecast only in forecast statuses).
CREATE TABLE PROJECT_REQUIREMENT (
    project_id      INTEGER NOT NULL REFERENCES PROJECT (id),
    requirement_id  INTEGER NOT NULL REFERENCES CAPABILITY_REQUIREMENT (id),
    quantity        INTEGER NOT NULL CHECK (quantity BETWEEN 0 AND 100000),
    created_at      TEXT    NOT NULL,
    PRIMARY KEY (project_id, requirement_id)
);
CREATE INDEX ix_project_requirement_req ON PROJECT_REQUIREMENT (requirement_id);

CREATE TABLE PROJECT_MODEL (
    project_id      INTEGER NOT NULL REFERENCES PROJECT (id),
    model_id        INTEGER NOT NULL REFERENCES CAPABILITY_MODEL (id),
    relation        TEXT    NOT NULL CHECK (relation IN ('CREATE', 'UPGRADE', 'REPLACE')),
    created_at      TEXT    NOT NULL,
    PRIMARY KEY (project_id, model_id)
);
CREATE INDEX ix_project_model_model ON PROJECT_MODEL (model_id);

-- Health indicators that cannot be derived from records (scope, procurement): a RAG with its stated reason.
CREATE TABLE PROJECT_HEALTH_NOTE (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id      INTEGER NOT NULL REFERENCES PROJECT (id),
    dimension       TEXT    NOT NULL CHECK (dimension IN ('SCOPE', 'PROCUREMENT')),
    rag             TEXT    NOT NULL CHECK (rag IN ('GREEN', 'AMBER', 'RED')),
    reason_en       TEXT    CHECK (reason_en IS NULL OR length(reason_en) <= 2000),
    reason_ar       TEXT    CHECK (reason_ar IS NULL OR length(reason_ar) <= 2000),
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL,
    created_by      INTEGER NOT NULL REFERENCES APP_USER (id),
    updated_by      INTEGER NOT NULL REFERENCES APP_USER (id),
    version         INTEGER NOT NULL DEFAULT 1,
    UNIQUE (project_id, dimension)
);

CREATE TABLE MILESTONE (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id          INTEGER NOT NULL REFERENCES PROJECT (id),
    stage_id            INTEGER REFERENCES WORKFLOW_STAGE (id),
    name_en             TEXT    NOT NULL CHECK (length(name_en) BETWEEN 1 AND 200),
    name_ar             TEXT    NOT NULL CHECK (length(name_ar) BETWEEN 1 AND 200),
    owner_name          TEXT    CHECK (owner_name IS NULL OR length(owner_name) <= 160),
    planned_start_date  TEXT    NOT NULL CHECK (planned_start_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    planned_end_date    TEXT    NOT NULL CHECK (planned_end_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    actual_end_date     TEXT    CHECK (actual_end_date IS NULL OR actual_end_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    forecast_end_date   TEXT    CHECK (forecast_end_date IS NULL OR forecast_end_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    status_code         TEXT    NOT NULL CHECK (length(status_code) BETWEEN 2 AND 30),
    progress_pct        INTEGER NOT NULL DEFAULT 0 CHECK (progress_pct BETWEEN 0 AND 100),
    is_major            INTEGER NOT NULL DEFAULT 0 CHECK (is_major IN (0, 1)),
    sort_order          INTEGER NOT NULL DEFAULT 0,
    created_at          TEXT    NOT NULL,
    updated_at          TEXT    NOT NULL,
    created_by          INTEGER NOT NULL REFERENCES APP_USER (id),
    updated_by          INTEGER NOT NULL REFERENCES APP_USER (id),
    version             INTEGER NOT NULL DEFAULT 1,
    archived_at         TEXT,
    archived_by         INTEGER REFERENCES APP_USER (id),
    CHECK (planned_end_date >= planned_start_date)
);
CREATE INDEX ix_milestone_project ON MILESTONE (project_id, sort_order);

CREATE TABLE RISK (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    code                TEXT    NOT NULL UNIQUE CHECK (length(code) BETWEEN 2 AND 20 AND code NOT GLOB '*[^-A-Z0-9]*'),
    project_id          INTEGER NOT NULL REFERENCES PROJECT (id),
    title_en            TEXT    NOT NULL CHECK (length(title_en) BETWEEN 2 AND 500),
    title_ar            TEXT    NOT NULL CHECK (length(title_ar) BETWEEN 2 AND 500),
    category            TEXT    NOT NULL CHECK (category IN ('TECHNICAL', 'SCHEDULE', 'FINANCIAL', 'SUPPLY_CHAIN',
                            'COMMERCIAL', 'OPERATIONAL', 'ENVIRONMENTAL', 'REGULATORY')),
    probability         INTEGER NOT NULL CHECK (probability BETWEEN 1 AND 5),
    impact              INTEGER NOT NULL CHECK (impact BETWEEN 1 AND 5),
    owner_name          TEXT    CHECK (owner_name IS NULL OR length(owner_name) <= 160),
    mitigation_en       TEXT    CHECK (mitigation_en IS NULL OR length(mitigation_en) <= 2000),
    mitigation_ar       TEXT    CHECK (mitigation_ar IS NULL OR length(mitigation_ar) <= 2000),
    mitigation_due_date TEXT    CHECK (mitigation_due_date IS NULL OR mitigation_due_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    status_code         TEXT    NOT NULL CHECK (length(status_code) BETWEEN 2 AND 30),
    created_at          TEXT    NOT NULL,
    updated_at          TEXT    NOT NULL,
    created_by          INTEGER NOT NULL REFERENCES APP_USER (id),
    updated_by          INTEGER NOT NULL REFERENCES APP_USER (id),
    version             INTEGER NOT NULL DEFAULT 1,
    archived_at         TEXT,
    archived_by         INTEGER REFERENCES APP_USER (id)
);
CREATE INDEX ix_risk_project ON RISK (project_id);

CREATE TABLE ISSUE (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    code                TEXT    NOT NULL UNIQUE CHECK (length(code) BETWEEN 2 AND 20 AND code NOT GLOB '*[^-A-Z0-9]*'),
    project_id          INTEGER NOT NULL REFERENCES PROJECT (id),
    title_en            TEXT    NOT NULL CHECK (length(title_en) BETWEEN 2 AND 500),
    title_ar            TEXT    NOT NULL CHECK (length(title_ar) BETWEEN 2 AND 500),
    severity            TEXT    NOT NULL CHECK (severity IN ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW')),
    owner_name          TEXT    CHECK (owner_name IS NULL OR length(owner_name) <= 160),
    raised_date         TEXT    NOT NULL CHECK (raised_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    target_date         TEXT    CHECK (target_date IS NULL OR target_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    is_escalated        INTEGER NOT NULL DEFAULT 0 CHECK (is_escalated IN (0, 1)),
    status_code         TEXT    NOT NULL CHECK (length(status_code) BETWEEN 2 AND 30),
    resolution_en       TEXT    CHECK (resolution_en IS NULL OR length(resolution_en) <= 2000),
    resolution_ar       TEXT    CHECK (resolution_ar IS NULL OR length(resolution_ar) <= 2000),
    created_at          TEXT    NOT NULL,
    updated_at          TEXT    NOT NULL,
    created_by          INTEGER NOT NULL REFERENCES APP_USER (id),
    updated_by          INTEGER NOT NULL REFERENCES APP_USER (id),
    version             INTEGER NOT NULL DEFAULT 1,
    archived_at         TEXT,
    archived_by         INTEGER REFERENCES APP_USER (id)
);
CREATE INDEX ix_issue_project ON ISSUE (project_id);

-- ---------------------------------------------------------------- history -----------------------------------------
-- Point-in-time KPI values (month-end and daily), for month / quarter / year trends. department_id and category_id
-- are NULL for "all".
CREATE TABLE METRIC_SNAPSHOT (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_date   TEXT    NOT NULL CHECK (snapshot_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    metric          TEXT    NOT NULL CHECK (length(metric) BETWEEN 2 AND 60),
    department_id   INTEGER REFERENCES DEPARTMENT (id),
    category_id     INTEGER REFERENCES CAPABILITY_CATEGORY (id),
    value           REAL    NOT NULL,
    created_at      TEXT    NOT NULL
);
CREATE INDEX ix_metric_snapshot ON METRIC_SNAPSHOT (metric, snapshot_date);
