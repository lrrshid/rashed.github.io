-- Testing & evaluation, maintenance & technical readiness, AI capability, development potential.
-- Twin of db/sqlite/V002__testing_maintenance_ai.sql. Runtime grants: docs/oracle-migration.md section 3.

CREATE SEQUENCE test_event_seq START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE TABLE test_event (
    id              NUMBER(19,0)        NOT NULL,
    code            VARCHAR2(20 CHAR)   NOT NULL,
    title_en        VARCHAR2(200 CHAR)  NOT NULL,
    title_ar        VARCHAR2(200 CHAR)  NOT NULL,
    model_id        NUMBER(19,0)        NOT NULL,
    asset_id        NUMBER(19,0),
    project_id      NUMBER(19,0),
    department_id   NUMBER(19,0)        NOT NULL,
    site_id         NUMBER(19,0),
    test_type       VARCHAR2(10 CHAR)   NOT NULL,
    test_date       DATE                NOT NULL,
    status_code     VARCHAR2(30 CHAR)   NOT NULL,
    score           NUMBER(3,0),
    result_en       CLOB,
    result_ar       CLOB,
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at      TIMESTAMP WITH TIME ZONE NOT NULL,
    created_by      NUMBER(19,0)        NOT NULL,
    updated_by      NUMBER(19,0)        NOT NULL,
    version         NUMBER(19,0)        DEFAULT 1 NOT NULL,
    archived_at     TIMESTAMP WITH TIME ZONE,
    archived_by     NUMBER(19,0),
    CONSTRAINT pk_test_event PRIMARY KEY (id),
    CONSTRAINT uq_test_event_code UNIQUE (code),
    CONSTRAINT ck_test_event_code CHECK (REGEXP_LIKE(code, '^[A-Z0-9-]{2,20}$')),
    CONSTRAINT ck_test_event_type CHECK (test_type IN ('INTERNAL', 'EXTERNAL')),
    CONSTRAINT ck_test_event_date CHECK (test_date = TRUNC(test_date)),
    CONSTRAINT ck_test_event_score CHECK (score IS NULL OR score BETWEEN 0 AND 100),
    CONSTRAINT ck_test_event_texts CHECK ((result_en IS NULL OR LENGTH(result_en) <= 2000)
        AND (result_ar IS NULL OR LENGTH(result_ar) <= 2000)),
    CONSTRAINT fk_test_event_model FOREIGN KEY (model_id) REFERENCES capability_model (id),
    CONSTRAINT fk_test_event_asset FOREIGN KEY (asset_id) REFERENCES asset (id),
    CONSTRAINT fk_test_event_project FOREIGN KEY (project_id) REFERENCES project (id),
    CONSTRAINT fk_test_event_department FOREIGN KEY (department_id) REFERENCES department (id),
    CONSTRAINT fk_test_event_site FOREIGN KEY (site_id) REFERENCES site (id),
    CONSTRAINT fk_test_event_created_by FOREIGN KEY (created_by) REFERENCES app_user (id),
    CONSTRAINT fk_test_event_updated_by FOREIGN KEY (updated_by) REFERENCES app_user (id),
    CONSTRAINT fk_test_event_archived_by FOREIGN KEY (archived_by) REFERENCES app_user (id)
);
CREATE INDEX ix_test_event_model ON test_event (model_id, test_date);
CREATE INDEX ix_test_event_project ON test_event (project_id);
CREATE INDEX ix_test_event_department ON test_event (department_id);

CREATE SEQUENCE maintenance_order_seq START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE TABLE maintenance_order (
    id                  NUMBER(19,0)        NOT NULL,
    code                VARCHAR2(20 CHAR)   NOT NULL,
    asset_id            NUMBER(19,0)        NOT NULL,
    maint_type          VARCHAR2(12 CHAR)   NOT NULL,
    title_en            VARCHAR2(200 CHAR)  NOT NULL,
    title_ar            VARCHAR2(200 CHAR)  NOT NULL,
    status_code         VARCHAR2(30 CHAR)   NOT NULL,
    start_date          DATE                NOT NULL,
    expected_end_date   DATE,
    actual_end_date     DATE,
    progress_pct        NUMBER(3,0)         DEFAULT 0 NOT NULL,
    cost                NUMBER(16,2),
    parts_shortage      NUMBER(1)           DEFAULT 0 NOT NULL,
    parts_text          VARCHAR2(500 CHAR),
    performed_by        VARCHAR2(160 CHAR),
    created_at          TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at          TIMESTAMP WITH TIME ZONE NOT NULL,
    created_by          NUMBER(19,0)        NOT NULL,
    updated_by          NUMBER(19,0)        NOT NULL,
    version             NUMBER(19,0)        DEFAULT 1 NOT NULL,
    archived_at         TIMESTAMP WITH TIME ZONE,
    archived_by         NUMBER(19,0),
    CONSTRAINT pk_maintenance_order PRIMARY KEY (id),
    CONSTRAINT uq_maintenance_order_code UNIQUE (code),
    CONSTRAINT ck_maintenance_order_code CHECK (REGEXP_LIKE(code, '^[A-Z0-9-]{2,20}$')),
    CONSTRAINT ck_maintenance_order_type CHECK (maint_type IN ('PREVENTIVE', 'CORRECTIVE', 'INSPECTION', 'UPGRADE')),
    CONSTRAINT ck_maintenance_order_dates CHECK (start_date = TRUNC(start_date)
        AND (expected_end_date IS NULL OR expected_end_date = TRUNC(expected_end_date))
        AND (actual_end_date IS NULL OR actual_end_date = TRUNC(actual_end_date))),
    CONSTRAINT ck_maintenance_order_progress CHECK (progress_pct BETWEEN 0 AND 100),
    CONSTRAINT ck_maintenance_order_cost CHECK (cost IS NULL OR cost >= 0),
    CONSTRAINT ck_maintenance_order_parts CHECK (parts_shortage IN (0, 1)),
    CONSTRAINT fk_maintenance_order_asset FOREIGN KEY (asset_id) REFERENCES asset (id),
    CONSTRAINT fk_maintenance_order_cby FOREIGN KEY (created_by) REFERENCES app_user (id),
    CONSTRAINT fk_maintenance_order_uby FOREIGN KEY (updated_by) REFERENCES app_user (id),
    CONSTRAINT fk_maintenance_order_aby FOREIGN KEY (archived_by) REFERENCES app_user (id)
);
CREATE INDEX ix_maintenance_order_asset ON maintenance_order (asset_id, start_date);

CREATE SEQUENCE ai_technology_seq START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE TABLE ai_technology (
    id              NUMBER(19,0)        NOT NULL,
    code            VARCHAR2(30 CHAR)   NOT NULL,
    name_en         VARCHAR2(120 CHAR)  NOT NULL,
    name_ar         VARCHAR2(120 CHAR)  NOT NULL,
    sort_order      NUMBER(10,0)        DEFAULT 0 NOT NULL,
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at      TIMESTAMP WITH TIME ZONE NOT NULL,
    created_by      NUMBER(19,0)        NOT NULL,
    updated_by      NUMBER(19,0)        NOT NULL,
    version         NUMBER(19,0)        DEFAULT 1 NOT NULL,
    archived_at     TIMESTAMP WITH TIME ZONE,
    archived_by     NUMBER(19,0),
    CONSTRAINT pk_ai_technology PRIMARY KEY (id),
    CONSTRAINT uq_ai_technology_code UNIQUE (code),
    CONSTRAINT ck_ai_technology_code CHECK (REGEXP_LIKE(code, '^[A-Z0-9_]{2,30}$')),
    CONSTRAINT fk_ai_technology_cby FOREIGN KEY (created_by) REFERENCES app_user (id),
    CONSTRAINT fk_ai_technology_uby FOREIGN KEY (updated_by) REFERENCES app_user (id),
    CONSTRAINT fk_ai_technology_aby FOREIGN KEY (archived_by) REFERENCES app_user (id)
);

CREATE TABLE model_ai_tech (
    model_id        NUMBER(19,0)        NOT NULL,
    technology_id   NUMBER(19,0)        NOT NULL,
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT pk_model_ai_tech PRIMARY KEY (model_id, technology_id),
    CONSTRAINT fk_model_ai_tech_model FOREIGN KEY (model_id) REFERENCES capability_model (id),
    CONSTRAINT fk_model_ai_tech_tech FOREIGN KEY (technology_id) REFERENCES ai_technology (id)
);
CREATE INDEX ix_model_ai_tech_tech ON model_ai_tech (technology_id);

CREATE SEQUENCE ai_level_criterion_seq START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE TABLE ai_level_criterion (
    id              NUMBER(19,0)        NOT NULL,
    ai_level        NUMBER(1,0)         NOT NULL,
    name_en         VARCHAR2(120 CHAR)  NOT NULL,
    name_ar         VARCHAR2(120 CHAR)  NOT NULL,
    description_en  VARCHAR2(500 CHAR),
    description_ar  VARCHAR2(500 CHAR),
    min_supported   NUMBER(3,0)         DEFAULT 0 NOT NULL,
    required_codes  VARCHAR2(500 CHAR),
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at      TIMESTAMP WITH TIME ZONE NOT NULL,
    created_by      NUMBER(19,0)        NOT NULL,
    updated_by      NUMBER(19,0)        NOT NULL,
    version         NUMBER(19,0)        DEFAULT 1 NOT NULL,
    CONSTRAINT pk_ai_level_criterion PRIMARY KEY (id),
    CONSTRAINT uq_ai_level_criterion_level UNIQUE (ai_level),
    CONSTRAINT ck_ai_level_criterion_level CHECK (ai_level BETWEEN 1 AND 5),
    CONSTRAINT ck_ai_level_criterion_min CHECK (min_supported BETWEEN 0 AND 100),
    CONSTRAINT fk_ai_level_criterion_cby FOREIGN KEY (created_by) REFERENCES app_user (id),
    CONSTRAINT fk_ai_level_criterion_uby FOREIGN KEY (updated_by) REFERENCES app_user (id)
);

CREATE SEQUENCE development_opportunity_seq START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE TABLE development_opportunity (
    id              NUMBER(19,0)        NOT NULL,
    code            VARCHAR2(20 CHAR)   NOT NULL,
    model_id        NUMBER(19,0)        NOT NULL,
    dev_type        VARCHAR2(20 CHAR)   NOT NULL,
    title_en        VARCHAR2(200 CHAR)  NOT NULL,
    title_ar        VARCHAR2(200 CHAR)  NOT NULL,
    benefit_en      VARCHAR2(500 CHAR),
    benefit_ar      VARCHAR2(500 CHAR),
    status_code     VARCHAR2(30 CHAR)   NOT NULL,
    complexity      VARCHAR2(10 CHAR)   NOT NULL,
    estimated_cost  NUMBER(16,2),
    duration_months NUMBER(3,0),
    priority        VARCHAR2(10 CHAR)   NOT NULL,
    project_id      NUMBER(19,0),
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at      TIMESTAMP WITH TIME ZONE NOT NULL,
    created_by      NUMBER(19,0)        NOT NULL,
    updated_by      NUMBER(19,0)        NOT NULL,
    version         NUMBER(19,0)        DEFAULT 1 NOT NULL,
    archived_at     TIMESTAMP WITH TIME ZONE,
    archived_by     NUMBER(19,0),
    CONSTRAINT pk_development_opportunity PRIMARY KEY (id),
    CONSTRAINT uq_development_opportunity_code UNIQUE (code),
    CONSTRAINT ck_development_opportunity_code CHECK (REGEXP_LIKE(code, '^[A-Z0-9-]{2,20}$')),
    CONSTRAINT ck_development_opportunity_type CHECK (dev_type IN ('AI', 'SENSORS', 'ENDURANCE', 'COMMUNICATIONS',
        'AUTONOMY', 'PAYLOAD', 'SECURITY', 'INTEGRATION', 'OTHER')),
    CONSTRAINT ck_development_opportunity_cx CHECK (complexity IN ('LOW', 'MEDIUM', 'HIGH')),
    CONSTRAINT ck_development_opportunity_pri CHECK (priority IN ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW')),
    CONSTRAINT ck_development_opportunity_num CHECK ((estimated_cost IS NULL OR estimated_cost >= 0)
        AND (duration_months IS NULL OR duration_months BETWEEN 0 AND 240)),
    CONSTRAINT fk_development_opportunity_mdl FOREIGN KEY (model_id) REFERENCES capability_model (id),
    CONSTRAINT fk_development_opportunity_prj FOREIGN KEY (project_id) REFERENCES project (id),
    CONSTRAINT fk_development_opportunity_cby FOREIGN KEY (created_by) REFERENCES app_user (id),
    CONSTRAINT fk_development_opportunity_uby FOREIGN KEY (updated_by) REFERENCES app_user (id),
    CONSTRAINT fk_development_opportunity_aby FOREIGN KEY (archived_by) REFERENCES app_user (id)
);
CREATE INDEX ix_development_opportunity_model ON development_opportunity (model_id);
