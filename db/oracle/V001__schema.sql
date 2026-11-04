-- Capability Portfolio Command: Oracle schema V001. Run by the schema owner (SQL*Plus / SQLcl); see docs/oracle-migration.md.
-- Twin of db/sqlite/V001__schema.sql (tables); indexes are in V002, the audit trigger in V003.
-- Conventions: ids NUMBER(19,0) from one sequence per table (INCREMENT BY 1, matching the application); instants
-- TIMESTAMP WITH TIME ZONE written as UTC; dates DATE (midnight); character lengths use CHAR semantics; money
-- NUMBER(16,2). No DROP statements and no demo records.

-- ---------------------------------------------------------------- security ----------------------------------------
CREATE SEQUENCE app_role_seq START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE TABLE app_role (
    id              NUMBER(19,0)        NOT NULL,
    code            VARCHAR2(30 CHAR)   NOT NULL,
    name_en         VARCHAR2(120 CHAR)  NOT NULL,
    name_ar         VARCHAR2(120 CHAR)  NOT NULL,
    scope           VARCHAR2(20 CHAR)   DEFAULT 'ALL' NOT NULL,
    is_system       NUMBER(1)           DEFAULT 0 NOT NULL,
    sort_order      NUMBER(10,0)        DEFAULT 0 NOT NULL,
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at      TIMESTAMP WITH TIME ZONE NOT NULL,
    version         NUMBER(19,0)        DEFAULT 1 NOT NULL,
    CONSTRAINT pk_app_role PRIMARY KEY (id),
    CONSTRAINT uq_app_role_code UNIQUE (code),
    CONSTRAINT ck_app_role_code CHECK (REGEXP_LIKE(code, '^[A-Z0-9_]{2,30}$')),
    CONSTRAINT ck_app_role_scope CHECK (scope IN ('ALL', 'DEPARTMENT')),
    CONSTRAINT ck_app_role_system CHECK (is_system IN (0, 1))
);

CREATE SEQUENCE app_user_seq START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE TABLE app_user (
    id              NUMBER(19,0)        NOT NULL,
    username        VARCHAR2(120 CHAR)  NOT NULL,
    display_name    VARCHAR2(160 CHAR)  NOT NULL,
    password_hash   VARCHAR2(255 CHAR)  NOT NULL,
    role_code       VARCHAR2(30 CHAR)   NOT NULL,
    is_active       NUMBER(1)           DEFAULT 1 NOT NULL,
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at      TIMESTAMP WITH TIME ZONE NOT NULL,
    version         NUMBER(19,0)        DEFAULT 1 NOT NULL,
    CONSTRAINT pk_app_user PRIMARY KEY (id),
    CONSTRAINT uq_app_user_username UNIQUE (username),
    CONSTRAINT ck_app_user_username CHECK (LENGTH(username) >= 2),
    CONSTRAINT ck_app_user_active CHECK (is_active IN (0, 1)),
    CONSTRAINT fk_app_user_role FOREIGN KEY (role_code) REFERENCES app_role (code)
);

CREATE TABLE role_permission (
    role_id         NUMBER(19,0)        NOT NULL,
    permission      VARCHAR2(30 CHAR)   NOT NULL,
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT pk_role_permission PRIMARY KEY (role_id, permission),
    CONSTRAINT fk_role_permission_role FOREIGN KEY (role_id) REFERENCES app_role (id),
    CONSTRAINT ck_role_permission CHECK (permission IN ('view', 'edit.requirements', 'edit.models', 'edit.assets',
        'edit.projects', 'edit.risks', 'edit.maintenance', 'edit.testing', 'edit.documents', 'reports.view',
        'reports.exec', 'reports.build', 'reports.schedule', 'export', 'admin'))
);

CREATE TABLE app_session (
    id              VARCHAR2(64 CHAR)   NOT NULL,
    user_id         NUMBER(19,0)        NOT NULL,
    csrf_token      VARCHAR2(64 CHAR)   NOT NULL,
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL,
    last_seen_at    TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT pk_app_session PRIMARY KEY (id),
    CONSTRAINT fk_app_session_user FOREIGN KEY (user_id) REFERENCES app_user (id),
    CONSTRAINT ck_app_session_id CHECK (LENGTH(id) = 64),
    CONSTRAINT ck_app_session_csrf CHECK (LENGTH(csrf_token) = 64)
);

CREATE SEQUENCE audit_event_seq START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE TABLE audit_event (
    id              NUMBER(19,0)        NOT NULL,
    actor_id        NUMBER(19,0)        NOT NULL,
    action          VARCHAR2(40 CHAR)   NOT NULL,
    entity_type     VARCHAR2(30 CHAR)   NOT NULL,
    entity_id       NUMBER(19,0)        NOT NULL,
    occurred_at     TIMESTAMP WITH TIME ZONE NOT NULL,
    before_json     CLOB,
    after_json      CLOB,
    reason          CLOB,
    CONSTRAINT pk_audit_event PRIMARY KEY (id),
    CONSTRAINT fk_audit_event_actor FOREIGN KEY (actor_id) REFERENCES app_user (id),
    CONSTRAINT ck_audit_event_type CHECK (REGEXP_LIKE(entity_type, '^[A-Z_]{2,30}$')),
    CONSTRAINT ck_audit_event_reason CHECK (reason IS NULL OR LENGTH(reason) <= 2000)
);

CREATE SEQUENCE app_setting_seq START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE TABLE app_setting (
    id              NUMBER(19,0)        NOT NULL,
    setting_key     VARCHAR2(60 CHAR)   NOT NULL,
    value_json      CLOB                NOT NULL,
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at      TIMESTAMP WITH TIME ZONE NOT NULL,
    created_by      NUMBER(19,0)        NOT NULL,
    updated_by      NUMBER(19,0)        NOT NULL,
    version         NUMBER(19,0)        DEFAULT 1 NOT NULL,
    CONSTRAINT pk_app_setting PRIMARY KEY (id),
    CONSTRAINT uq_app_setting_key UNIQUE (setting_key),
    CONSTRAINT ck_app_setting_key CHECK (REGEXP_LIKE(setting_key, '^[a-z0-9_.]{2,60}$')),
    CONSTRAINT ck_app_setting_value CHECK (LENGTH(value_json) <= 4000),
    CONSTRAINT fk_app_setting_created_by FOREIGN KEY (created_by) REFERENCES app_user (id),
    CONSTRAINT fk_app_setting_updated_by FOREIGN KEY (updated_by) REFERENCES app_user (id)
);

CREATE SEQUENCE saved_view_seq START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE TABLE saved_view (
    id              NUMBER(19,0)        NOT NULL,
    user_id         NUMBER(19,0)        NOT NULL,
    page            VARCHAR2(40 CHAR)   NOT NULL,
    name            VARCHAR2(80 CHAR)   NOT NULL,
    filters_json    CLOB                NOT NULL,
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT pk_saved_view PRIMARY KEY (id),
    CONSTRAINT fk_saved_view_user FOREIGN KEY (user_id) REFERENCES app_user (id),
    CONSTRAINT ck_saved_view_filters CHECK (LENGTH(filters_json) <= 4000)
);

-- ---------------------------------------------------------------- configurable lists ------------------------------
-- Every list table: code, bilingual name, sort order, the audit stamps, optimistic-lock version, archive columns.
CREATE SEQUENCE department_seq START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE TABLE department (
    id              NUMBER(19,0)        NOT NULL,
    code            VARCHAR2(20 CHAR)   NOT NULL,
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
    CONSTRAINT pk_department PRIMARY KEY (id),
    CONSTRAINT uq_department_code UNIQUE (code),
    CONSTRAINT ck_department_code CHECK (REGEXP_LIKE(code, '^[A-Z0-9-]{1,20}$')),
    CONSTRAINT fk_department_created_by FOREIGN KEY (created_by) REFERENCES app_user (id),
    CONSTRAINT fk_department_updated_by FOREIGN KEY (updated_by) REFERENCES app_user (id),
    CONSTRAINT fk_department_archived_by FOREIGN KEY (archived_by) REFERENCES app_user (id)
);

CREATE TABLE user_department (
    user_id         NUMBER(19,0)        NOT NULL,
    department_id   NUMBER(19,0)        NOT NULL,
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT pk_user_department PRIMARY KEY (user_id, department_id),
    CONSTRAINT fk_user_department_user FOREIGN KEY (user_id) REFERENCES app_user (id),
    CONSTRAINT fk_user_department_dept FOREIGN KEY (department_id) REFERENCES department (id)
);

CREATE SEQUENCE capability_category_seq START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE TABLE capability_category (
    id              NUMBER(19,0)        NOT NULL,
    code            VARCHAR2(20 CHAR)   NOT NULL,
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
    CONSTRAINT pk_capability_category PRIMARY KEY (id),
    CONSTRAINT uq_capability_category_code UNIQUE (code),
    CONSTRAINT ck_capability_category_code CHECK (REGEXP_LIKE(code, '^[A-Z0-9-]{1,20}$')),
    CONSTRAINT fk_capability_category_cby FOREIGN KEY (created_by) REFERENCES app_user (id),
    CONSTRAINT fk_capability_category_uby FOREIGN KEY (updated_by) REFERENCES app_user (id),
    CONSTRAINT fk_capability_category_aby FOREIGN KEY (archived_by) REFERENCES app_user (id)
);

CREATE SEQUENCE site_seq START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE TABLE site (
    id              NUMBER(19,0)        NOT NULL,
    code            VARCHAR2(20 CHAR)   NOT NULL,
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
    CONSTRAINT pk_site PRIMARY KEY (id),
    CONSTRAINT uq_site_code UNIQUE (code),
    CONSTRAINT ck_site_code CHECK (REGEXP_LIKE(code, '^[A-Z0-9-]{1,20}$')),
    CONSTRAINT fk_site_created_by FOREIGN KEY (created_by) REFERENCES app_user (id),
    CONSTRAINT fk_site_updated_by FOREIGN KEY (updated_by) REFERENCES app_user (id),
    CONSTRAINT fk_site_archived_by FOREIGN KEY (archived_by) REFERENCES app_user (id)
);

CREATE SEQUENCE organization_seq START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE TABLE organization (
    id              NUMBER(19,0)        NOT NULL,
    code            VARCHAR2(20 CHAR)   NOT NULL,
    name_en         VARCHAR2(160 CHAR)  NOT NULL,
    name_ar         VARCHAR2(160 CHAR)  NOT NULL,
    kind            VARCHAR2(20 CHAR)   NOT NULL,
    country_en      VARCHAR2(80 CHAR),
    country_ar      VARCHAR2(80 CHAR),
    sort_order      NUMBER(10,0)        DEFAULT 0 NOT NULL,
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at      TIMESTAMP WITH TIME ZONE NOT NULL,
    created_by      NUMBER(19,0)        NOT NULL,
    updated_by      NUMBER(19,0)        NOT NULL,
    version         NUMBER(19,0)        DEFAULT 1 NOT NULL,
    archived_at     TIMESTAMP WITH TIME ZONE,
    archived_by     NUMBER(19,0),
    CONSTRAINT pk_organization PRIMARY KEY (id),
    CONSTRAINT uq_organization_code UNIQUE (code),
    CONSTRAINT ck_organization_code CHECK (REGEXP_LIKE(code, '^[A-Z0-9-]{1,20}$')),
    CONSTRAINT ck_organization_kind CHECK (kind IN ('MANUFACTURER', 'SUPPLIER', 'BOTH')),
    CONSTRAINT fk_organization_created_by FOREIGN KEY (created_by) REFERENCES app_user (id),
    CONSTRAINT fk_organization_updated_by FOREIGN KEY (updated_by) REFERENCES app_user (id),
    CONSTRAINT fk_organization_archived_by FOREIGN KEY (archived_by) REFERENCES app_user (id)
);

CREATE SEQUENCE status_def_seq START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE TABLE status_def (
    id              NUMBER(19,0)        NOT NULL,
    status_domain   VARCHAR2(20 CHAR)   NOT NULL,
    code            VARCHAR2(30 CHAR)   NOT NULL,
    name_en         VARCHAR2(120 CHAR)  NOT NULL,
    name_ar         VARCHAR2(120 CHAR)  NOT NULL,
    color           VARCHAR2(10 CHAR)   DEFAULT 'grey' NOT NULL,
    is_terminal     NUMBER(1)           DEFAULT 0 NOT NULL,
    sort_order      NUMBER(10,0)        DEFAULT 0 NOT NULL,
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at      TIMESTAMP WITH TIME ZONE NOT NULL,
    created_by      NUMBER(19,0)        NOT NULL,
    updated_by      NUMBER(19,0)        NOT NULL,
    version         NUMBER(19,0)        DEFAULT 1 NOT NULL,
    archived_at     TIMESTAMP WITH TIME ZONE,
    archived_by     NUMBER(19,0),
    CONSTRAINT pk_status_def PRIMARY KEY (id),
    CONSTRAINT uq_status_def UNIQUE (status_domain, code),
    CONSTRAINT ck_status_def_domain CHECK (status_domain IN ('ASSET', 'PROJECT', 'MILESTONE', 'RISK', 'ISSUE', 'TEST',
        'MAINTENANCE', 'DEVELOPMENT')),
    CONSTRAINT ck_status_def_code CHECK (REGEXP_LIKE(code, '^[A-Z0-9_]{2,30}$')),
    CONSTRAINT ck_status_def_color CHECK (color IN ('green', 'amber', 'red', 'blue', 'purple', 'teal', 'grey',
        'orange', 'pink', 'dark')),
    CONSTRAINT ck_status_def_terminal CHECK (is_terminal IN (0, 1)),
    CONSTRAINT fk_status_def_created_by FOREIGN KEY (created_by) REFERENCES app_user (id),
    CONSTRAINT fk_status_def_updated_by FOREIGN KEY (updated_by) REFERENCES app_user (id),
    CONSTRAINT fk_status_def_archived_by FOREIGN KEY (archived_by) REFERENCES app_user (id)
);

CREATE SEQUENCE project_type_seq START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE TABLE project_type (
    id              NUMBER(19,0)        NOT NULL,
    code            VARCHAR2(30 CHAR)   NOT NULL,
    name_en         VARCHAR2(120 CHAR)  NOT NULL,
    name_ar         VARCHAR2(120 CHAR)  NOT NULL,
    color           VARCHAR2(10 CHAR)   DEFAULT 'blue' NOT NULL,
    sort_order      NUMBER(10,0)        DEFAULT 0 NOT NULL,
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at      TIMESTAMP WITH TIME ZONE NOT NULL,
    created_by      NUMBER(19,0)        NOT NULL,
    updated_by      NUMBER(19,0)        NOT NULL,
    version         NUMBER(19,0)        DEFAULT 1 NOT NULL,
    archived_at     TIMESTAMP WITH TIME ZONE,
    archived_by     NUMBER(19,0),
    CONSTRAINT pk_project_type PRIMARY KEY (id),
    CONSTRAINT uq_project_type_code UNIQUE (code),
    CONSTRAINT ck_project_type_code CHECK (REGEXP_LIKE(code, '^[A-Z0-9_]{2,30}$')),
    CONSTRAINT ck_project_type_color CHECK (color IN ('green', 'amber', 'red', 'blue', 'purple', 'teal', 'grey',
        'orange', 'pink', 'dark')),
    CONSTRAINT fk_project_type_created_by FOREIGN KEY (created_by) REFERENCES app_user (id),
    CONSTRAINT fk_project_type_updated_by FOREIGN KEY (updated_by) REFERENCES app_user (id),
    CONSTRAINT fk_project_type_archived_by FOREIGN KEY (archived_by) REFERENCES app_user (id)
);

CREATE SEQUENCE workflow_stage_seq START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE TABLE workflow_stage (
    id              NUMBER(19,0)        NOT NULL,
    project_type_id NUMBER(19,0)        NOT NULL,
    name_en         VARCHAR2(120 CHAR)  NOT NULL,
    name_ar         VARCHAR2(120 CHAR)  NOT NULL,
    sort_order      NUMBER(10,0)        NOT NULL,
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at      TIMESTAMP WITH TIME ZONE NOT NULL,
    created_by      NUMBER(19,0)        NOT NULL,
    updated_by      NUMBER(19,0)        NOT NULL,
    version         NUMBER(19,0)        DEFAULT 1 NOT NULL,
    archived_at     TIMESTAMP WITH TIME ZONE,
    archived_by     NUMBER(19,0),
    CONSTRAINT pk_workflow_stage PRIMARY KEY (id),
    CONSTRAINT fk_workflow_stage_type FOREIGN KEY (project_type_id) REFERENCES project_type (id),
    CONSTRAINT fk_workflow_stage_created_by FOREIGN KEY (created_by) REFERENCES app_user (id),
    CONSTRAINT fk_workflow_stage_updated_by FOREIGN KEY (updated_by) REFERENCES app_user (id),
    CONSTRAINT fk_workflow_stage_archived_by FOREIGN KEY (archived_by) REFERENCES app_user (id)
);

CREATE SEQUENCE spec_field_seq START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE TABLE spec_field (
    id              NUMBER(19,0)        NOT NULL,
    category_id     NUMBER(19,0)        NOT NULL,
    section         VARCHAR2(20 CHAR)   NOT NULL,
    code            VARCHAR2(40 CHAR)   NOT NULL,
    name_en         VARCHAR2(120 CHAR)  NOT NULL,
    name_ar         VARCHAR2(120 CHAR)  NOT NULL,
    unit            VARCHAR2(20 CHAR),
    data_type       VARCHAR2(10 CHAR)   NOT NULL,
    is_custom       NUMBER(1)           DEFAULT 0 NOT NULL,
    sort_order      NUMBER(10,0)        DEFAULT 0 NOT NULL,
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at      TIMESTAMP WITH TIME ZONE NOT NULL,
    created_by      NUMBER(19,0)        NOT NULL,
    updated_by      NUMBER(19,0)        NOT NULL,
    version         NUMBER(19,0)        DEFAULT 1 NOT NULL,
    archived_at     TIMESTAMP WITH TIME ZONE,
    archived_by     NUMBER(19,0),
    CONSTRAINT pk_spec_field PRIMARY KEY (id),
    CONSTRAINT uq_spec_field UNIQUE (category_id, code),
    CONSTRAINT fk_spec_field_category FOREIGN KEY (category_id) REFERENCES capability_category (id),
    CONSTRAINT ck_spec_field_section CHECK (section IN ('PERFORMANCE', 'SENSORS', 'COMMUNICATIONS', 'ENVIRONMENT', 'OTHER')),
    CONSTRAINT ck_spec_field_code CHECK (REGEXP_LIKE(code, '^[a-z0-9_]{2,40}$')),
    CONSTRAINT ck_spec_field_type CHECK (data_type IN ('TEXT', 'NUMBER', 'BOOL')),
    CONSTRAINT ck_spec_field_custom CHECK (is_custom IN (0, 1)),
    CONSTRAINT fk_spec_field_created_by FOREIGN KEY (created_by) REFERENCES app_user (id),
    CONSTRAINT fk_spec_field_updated_by FOREIGN KEY (updated_by) REFERENCES app_user (id),
    CONSTRAINT fk_spec_field_archived_by FOREIGN KEY (archived_by) REFERENCES app_user (id)
);

-- ---------------------------------------------------------------- capability records ------------------------------
CREATE SEQUENCE capability_requirement_seq START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE TABLE capability_requirement (
    id              NUMBER(19,0)        NOT NULL,
    code            VARCHAR2(20 CHAR)   NOT NULL,
    name_en         VARCHAR2(200 CHAR)  NOT NULL,
    name_ar         VARCHAR2(200 CHAR)  NOT NULL,
    department_id   NUMBER(19,0)        NOT NULL,
    category_id     NUMBER(19,0)        NOT NULL,
    required_qty    NUMBER(10,0)        NOT NULL,
    priority        VARCHAR2(10 CHAR)   NOT NULL,
    target_date     DATE,
    notes           CLOB,
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at      TIMESTAMP WITH TIME ZONE NOT NULL,
    created_by      NUMBER(19,0)        NOT NULL,
    updated_by      NUMBER(19,0)        NOT NULL,
    version         NUMBER(19,0)        DEFAULT 1 NOT NULL,
    archived_at     TIMESTAMP WITH TIME ZONE,
    archived_by     NUMBER(19,0),
    CONSTRAINT pk_capability_requirement PRIMARY KEY (id),
    CONSTRAINT uq_capability_requirement_code UNIQUE (code),
    CONSTRAINT ck_capability_requirement_code CHECK (REGEXP_LIKE(code, '^[A-Z0-9-]{2,20}$')),
    CONSTRAINT ck_capability_requirement_qty CHECK (required_qty BETWEEN 0 AND 100000),
    CONSTRAINT ck_capability_requirement_prio CHECK (priority IN ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW')),
    CONSTRAINT ck_capability_requirement_date CHECK (target_date IS NULL OR target_date = TRUNC(target_date)),
    CONSTRAINT ck_capability_requirement_notes CHECK (notes IS NULL OR LENGTH(notes) <= 4000),
    CONSTRAINT fk_capability_requirement_dept FOREIGN KEY (department_id) REFERENCES department (id),
    CONSTRAINT fk_capability_requirement_cat FOREIGN KEY (category_id) REFERENCES capability_category (id),
    CONSTRAINT fk_capability_requirement_cby FOREIGN KEY (created_by) REFERENCES app_user (id),
    CONSTRAINT fk_capability_requirement_uby FOREIGN KEY (updated_by) REFERENCES app_user (id),
    CONSTRAINT fk_capability_requirement_aby FOREIGN KEY (archived_by) REFERENCES app_user (id)
);

CREATE SEQUENCE capability_model_seq START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE TABLE capability_model (
    id              NUMBER(19,0)        NOT NULL,
    code            VARCHAR2(20 CHAR)   NOT NULL,
    name_en         VARCHAR2(160 CHAR)  NOT NULL,
    name_ar         VARCHAR2(160 CHAR)  NOT NULL,
    category_id     NUMBER(19,0)        NOT NULL,
    manufacturer_id NUMBER(19,0),
    role_en         VARCHAR2(200 CHAR),
    role_ar         VARCHAR2(200 CHAR),
    unit_cost       NUMBER(16,2),
    specs_json      CLOB,
    notes           CLOB,
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at      TIMESTAMP WITH TIME ZONE NOT NULL,
    created_by      NUMBER(19,0)        NOT NULL,
    updated_by      NUMBER(19,0)        NOT NULL,
    version         NUMBER(19,0)        DEFAULT 1 NOT NULL,
    archived_at     TIMESTAMP WITH TIME ZONE,
    archived_by     NUMBER(19,0),
    CONSTRAINT pk_capability_model PRIMARY KEY (id),
    CONSTRAINT uq_capability_model_code UNIQUE (code),
    CONSTRAINT ck_capability_model_code CHECK (REGEXP_LIKE(code, '^[A-Z0-9-]{2,20}$')),
    CONSTRAINT ck_capability_model_cost CHECK (unit_cost IS NULL OR unit_cost >= 0),
    CONSTRAINT ck_capability_model_specs CHECK (specs_json IS NULL OR LENGTH(specs_json) <= 4000),
    CONSTRAINT ck_capability_model_notes CHECK (notes IS NULL OR LENGTH(notes) <= 4000),
    CONSTRAINT fk_capability_model_cat FOREIGN KEY (category_id) REFERENCES capability_category (id),
    CONSTRAINT fk_capability_model_mfr FOREIGN KEY (manufacturer_id) REFERENCES organization (id),
    CONSTRAINT fk_capability_model_cby FOREIGN KEY (created_by) REFERENCES app_user (id),
    CONSTRAINT fk_capability_model_uby FOREIGN KEY (updated_by) REFERENCES app_user (id),
    CONSTRAINT fk_capability_model_aby FOREIGN KEY (archived_by) REFERENCES app_user (id)
);

CREATE TABLE requirement_model (
    requirement_id  NUMBER(19,0)        NOT NULL,
    model_id        NUMBER(19,0)        NOT NULL,
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT pk_requirement_model PRIMARY KEY (requirement_id, model_id),
    CONSTRAINT fk_requirement_model_req FOREIGN KEY (requirement_id) REFERENCES capability_requirement (id),
    CONSTRAINT fk_requirement_model_model FOREIGN KEY (model_id) REFERENCES capability_model (id)
);

CREATE SEQUENCE contract_seq START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE TABLE contract (
    id              NUMBER(19,0)        NOT NULL,
    code            VARCHAR2(30 CHAR)   NOT NULL,
    title_en        VARCHAR2(200 CHAR)  NOT NULL,
    title_ar        VARCHAR2(200 CHAR)  NOT NULL,
    supplier_id     NUMBER(19,0),
    contract_value  NUMBER(16,2),
    start_date      DATE,
    end_date        DATE,
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at      TIMESTAMP WITH TIME ZONE NOT NULL,
    created_by      NUMBER(19,0)        NOT NULL,
    updated_by      NUMBER(19,0)        NOT NULL,
    version         NUMBER(19,0)        DEFAULT 1 NOT NULL,
    archived_at     TIMESTAMP WITH TIME ZONE,
    archived_by     NUMBER(19,0),
    CONSTRAINT pk_contract PRIMARY KEY (id),
    CONSTRAINT uq_contract_code UNIQUE (code),
    CONSTRAINT ck_contract_code CHECK (REGEXP_LIKE(code, '^[A-Z0-9-]{2,30}$')),
    CONSTRAINT ck_contract_value CHECK (contract_value IS NULL OR contract_value >= 0),
    CONSTRAINT ck_contract_dates CHECK ((start_date IS NULL OR start_date = TRUNC(start_date))
                                        AND (end_date IS NULL OR end_date = TRUNC(end_date))),
    CONSTRAINT fk_contract_supplier FOREIGN KEY (supplier_id) REFERENCES organization (id),
    CONSTRAINT fk_contract_created_by FOREIGN KEY (created_by) REFERENCES app_user (id),
    CONSTRAINT fk_contract_updated_by FOREIGN KEY (updated_by) REFERENCES app_user (id),
    CONSTRAINT fk_contract_archived_by FOREIGN KEY (archived_by) REFERENCES app_user (id)
);

CREATE SEQUENCE asset_seq START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE TABLE asset (
    id                      NUMBER(19,0)        NOT NULL,
    code                    VARCHAR2(30 CHAR)   NOT NULL,
    serial_number           VARCHAR2(60 CHAR),
    model_id                NUMBER(19,0)        NOT NULL,
    department_id           NUMBER(19,0)        NOT NULL,
    site_id                 NUMBER(19,0),
    status_code             VARCHAR2(30 CHAR)   NOT NULL,
    readiness_operational   NUMBER(3,0),
    readiness_technical     NUMBER(3,0),
    readiness_mission       NUMBER(3,0),
    readiness_maintenance   NUMBER(3,0),
    acquisition_date        DATE,
    expected_delivery_date  DATE,
    acquisition_method      VARCHAR2(20 CHAR),
    contract_id             NUMBER(19,0),
    warranty_end_date       DATE,
    unit_value              NUMBER(16,2),
    service_life_years      NUMBER(3,0),
    operating_hours         NUMBER(10,0),
    responsible_en          VARCHAR2(160 CHAR),
    responsible_ar          VARCHAR2(160 CHAR),
    notes                   CLOB,
    created_at              TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at              TIMESTAMP WITH TIME ZONE NOT NULL,
    created_by              NUMBER(19,0)        NOT NULL,
    updated_by              NUMBER(19,0)        NOT NULL,
    version                 NUMBER(19,0)        DEFAULT 1 NOT NULL,
    archived_at             TIMESTAMP WITH TIME ZONE,
    archived_by             NUMBER(19,0),
    CONSTRAINT pk_asset PRIMARY KEY (id),
    CONSTRAINT uq_asset_code UNIQUE (code),
    CONSTRAINT ck_asset_code CHECK (REGEXP_LIKE(code, '^[A-Z0-9-]{2,30}$')),
    CONSTRAINT ck_asset_readiness CHECK ((readiness_operational IS NULL OR readiness_operational BETWEEN 0 AND 100)
        AND (readiness_technical IS NULL OR readiness_technical BETWEEN 0 AND 100)
        AND (readiness_mission IS NULL OR readiness_mission BETWEEN 0 AND 100)
        AND (readiness_maintenance IS NULL OR readiness_maintenance BETWEEN 0 AND 100)),
    CONSTRAINT ck_asset_method CHECK (acquisition_method IS NULL OR acquisition_method IN ('DIRECT_CONTRACT',
        'TENDER', 'GOVERNMENT', 'DONATION', 'DEVELOPMENT', 'OTHER')),
    CONSTRAINT ck_asset_dates CHECK ((acquisition_date IS NULL OR acquisition_date = TRUNC(acquisition_date))
        AND (expected_delivery_date IS NULL OR expected_delivery_date = TRUNC(expected_delivery_date))
        AND (warranty_end_date IS NULL OR warranty_end_date = TRUNC(warranty_end_date))),
    CONSTRAINT ck_asset_numbers CHECK ((unit_value IS NULL OR unit_value >= 0)
        AND (service_life_years IS NULL OR service_life_years >= 0) AND (operating_hours IS NULL OR operating_hours >= 0)),
    CONSTRAINT ck_asset_notes CHECK (notes IS NULL OR LENGTH(notes) <= 4000),
    CONSTRAINT fk_asset_model FOREIGN KEY (model_id) REFERENCES capability_model (id),
    CONSTRAINT fk_asset_department FOREIGN KEY (department_id) REFERENCES department (id),
    CONSTRAINT fk_asset_site FOREIGN KEY (site_id) REFERENCES site (id),
    CONSTRAINT fk_asset_contract FOREIGN KEY (contract_id) REFERENCES contract (id),
    CONSTRAINT fk_asset_created_by FOREIGN KEY (created_by) REFERENCES app_user (id),
    CONSTRAINT fk_asset_updated_by FOREIGN KEY (updated_by) REFERENCES app_user (id),
    CONSTRAINT fk_asset_archived_by FOREIGN KEY (archived_by) REFERENCES app_user (id)
);

CREATE SEQUENCE asset_status_history_seq START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE TABLE asset_status_history (
    id              NUMBER(19,0)        NOT NULL,
    asset_id        NUMBER(19,0)        NOT NULL,
    status_code     VARCHAR2(30 CHAR)   NOT NULL,
    readiness       NUMBER(3,0),
    changed_at      TIMESTAMP WITH TIME ZONE NOT NULL,
    changed_by      NUMBER(19,0)        NOT NULL,
    note            CLOB,
    CONSTRAINT pk_asset_status_history PRIMARY KEY (id),
    CONSTRAINT fk_asset_status_history_asset FOREIGN KEY (asset_id) REFERENCES asset (id),
    CONSTRAINT fk_asset_status_history_by FOREIGN KEY (changed_by) REFERENCES app_user (id),
    CONSTRAINT ck_asset_status_history_rd CHECK (readiness IS NULL OR readiness BETWEEN 0 AND 100),
    CONSTRAINT ck_asset_status_history_note CHECK (note IS NULL OR LENGTH(note) <= 2000)
);

-- ---------------------------------------------------------------- projects ----------------------------------------
CREATE SEQUENCE project_seq START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE TABLE project (
    id                  NUMBER(19,0)        NOT NULL,
    code                VARCHAR2(20 CHAR)   NOT NULL,
    name_en             VARCHAR2(200 CHAR)  NOT NULL,
    name_ar             VARCHAR2(200 CHAR)  NOT NULL,
    project_type_id     NUMBER(19,0)        NOT NULL,
    department_id       NUMBER(19,0)        NOT NULL,
    category_id         NUMBER(19,0)        NOT NULL,
    status_code         VARCHAR2(30 CHAR)   NOT NULL,
    stage_id            NUMBER(19,0),
    manager_name        VARCHAR2(160 CHAR),
    supplier_id         NUMBER(19,0),
    contract_id         NUMBER(19,0),
    budget              NUMBER(16,2),
    committed           NUMBER(16,2),
    actual_spend        NUMBER(16,2),
    progress_pct        NUMBER(3,0)         DEFAULT 0 NOT NULL,
    start_date          DATE,
    baseline_end_date   DATE,
    target_end_date     DATE,
    forecast_end_date   DATE,
    actual_end_date     DATE,
    next_action_en      CLOB,
    next_action_ar      CLOB,
    notes_en            CLOB,
    notes_ar            CLOB,
    created_at          TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at          TIMESTAMP WITH TIME ZONE NOT NULL,
    created_by          NUMBER(19,0)        NOT NULL,
    updated_by          NUMBER(19,0)        NOT NULL,
    version             NUMBER(19,0)        DEFAULT 1 NOT NULL,
    archived_at         TIMESTAMP WITH TIME ZONE,
    archived_by         NUMBER(19,0),
    CONSTRAINT pk_project PRIMARY KEY (id),
    CONSTRAINT uq_project_code UNIQUE (code),
    CONSTRAINT ck_project_code CHECK (REGEXP_LIKE(code, '^[A-Z0-9-]{2,20}$')),
    CONSTRAINT ck_project_money CHECK ((budget IS NULL OR budget >= 0) AND (committed IS NULL OR committed >= 0)
        AND (actual_spend IS NULL OR actual_spend >= 0)),
    CONSTRAINT ck_project_progress CHECK (progress_pct BETWEEN 0 AND 100),
    CONSTRAINT ck_project_dates CHECK ((start_date IS NULL OR start_date = TRUNC(start_date))
        AND (baseline_end_date IS NULL OR baseline_end_date = TRUNC(baseline_end_date))
        AND (target_end_date IS NULL OR target_end_date = TRUNC(target_end_date))
        AND (forecast_end_date IS NULL OR forecast_end_date = TRUNC(forecast_end_date))
        AND (actual_end_date IS NULL OR actual_end_date = TRUNC(actual_end_date))),
    CONSTRAINT ck_project_texts CHECK ((next_action_en IS NULL OR LENGTH(next_action_en) <= 2000)
        AND (next_action_ar IS NULL OR LENGTH(next_action_ar) <= 2000)
        AND (notes_en IS NULL OR LENGTH(notes_en) <= 4000) AND (notes_ar IS NULL OR LENGTH(notes_ar) <= 4000)),
    CONSTRAINT fk_project_type FOREIGN KEY (project_type_id) REFERENCES project_type (id),
    CONSTRAINT fk_project_department FOREIGN KEY (department_id) REFERENCES department (id),
    CONSTRAINT fk_project_category FOREIGN KEY (category_id) REFERENCES capability_category (id),
    CONSTRAINT fk_project_stage FOREIGN KEY (stage_id) REFERENCES workflow_stage (id),
    CONSTRAINT fk_project_supplier FOREIGN KEY (supplier_id) REFERENCES organization (id),
    CONSTRAINT fk_project_contract FOREIGN KEY (contract_id) REFERENCES contract (id),
    CONSTRAINT fk_project_created_by FOREIGN KEY (created_by) REFERENCES app_user (id),
    CONSTRAINT fk_project_updated_by FOREIGN KEY (updated_by) REFERENCES app_user (id),
    CONSTRAINT fk_project_archived_by FOREIGN KEY (archived_by) REFERENCES app_user (id)
);

CREATE TABLE project_requirement (
    project_id      NUMBER(19,0)        NOT NULL,
    requirement_id  NUMBER(19,0)        NOT NULL,
    quantity        NUMBER(10,0)        NOT NULL,
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT pk_project_requirement PRIMARY KEY (project_id, requirement_id),
    CONSTRAINT fk_project_requirement_prj FOREIGN KEY (project_id) REFERENCES project (id),
    CONSTRAINT fk_project_requirement_req FOREIGN KEY (requirement_id) REFERENCES capability_requirement (id),
    CONSTRAINT ck_project_requirement_qty CHECK (quantity BETWEEN 0 AND 100000)
);

CREATE TABLE project_model (
    project_id      NUMBER(19,0)        NOT NULL,
    model_id        NUMBER(19,0)        NOT NULL,
    relation        VARCHAR2(10 CHAR)   NOT NULL,
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT pk_project_model PRIMARY KEY (project_id, model_id),
    CONSTRAINT fk_project_model_prj FOREIGN KEY (project_id) REFERENCES project (id),
    CONSTRAINT fk_project_model_model FOREIGN KEY (model_id) REFERENCES capability_model (id),
    CONSTRAINT ck_project_model_relation CHECK (relation IN ('CREATE', 'UPGRADE', 'REPLACE'))
);

CREATE SEQUENCE project_health_note_seq START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE TABLE project_health_note (
    id              NUMBER(19,0)        NOT NULL,
    project_id      NUMBER(19,0)        NOT NULL,
    dimension       VARCHAR2(20 CHAR)   NOT NULL,
    rag             VARCHAR2(10 CHAR)   NOT NULL,
    reason_en       CLOB,
    reason_ar       CLOB,
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at      TIMESTAMP WITH TIME ZONE NOT NULL,
    created_by      NUMBER(19,0)        NOT NULL,
    updated_by      NUMBER(19,0)        NOT NULL,
    version         NUMBER(19,0)        DEFAULT 1 NOT NULL,
    CONSTRAINT pk_project_health_note PRIMARY KEY (id),
    CONSTRAINT uq_project_health_note UNIQUE (project_id, dimension),
    CONSTRAINT fk_project_health_note_prj FOREIGN KEY (project_id) REFERENCES project (id),
    CONSTRAINT ck_project_health_note_dim CHECK (dimension IN ('SCOPE', 'PROCUREMENT')),
    CONSTRAINT ck_project_health_note_rag CHECK (rag IN ('GREEN', 'AMBER', 'RED')),
    CONSTRAINT ck_project_health_note_text CHECK ((reason_en IS NULL OR LENGTH(reason_en) <= 2000)
        AND (reason_ar IS NULL OR LENGTH(reason_ar) <= 2000)),
    CONSTRAINT fk_project_health_note_cby FOREIGN KEY (created_by) REFERENCES app_user (id),
    CONSTRAINT fk_project_health_note_uby FOREIGN KEY (updated_by) REFERENCES app_user (id)
);

CREATE SEQUENCE milestone_seq START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE TABLE milestone (
    id                  NUMBER(19,0)        NOT NULL,
    project_id          NUMBER(19,0)        NOT NULL,
    stage_id            NUMBER(19,0),
    name_en             VARCHAR2(200 CHAR)  NOT NULL,
    name_ar             VARCHAR2(200 CHAR)  NOT NULL,
    owner_name          VARCHAR2(160 CHAR),
    planned_start_date  DATE                NOT NULL,
    planned_end_date    DATE                NOT NULL,
    actual_end_date     DATE,
    forecast_end_date   DATE,
    status_code         VARCHAR2(30 CHAR)   NOT NULL,
    progress_pct        NUMBER(3,0)         DEFAULT 0 NOT NULL,
    is_major            NUMBER(1)           DEFAULT 0 NOT NULL,
    sort_order          NUMBER(10,0)        DEFAULT 0 NOT NULL,
    created_at          TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at          TIMESTAMP WITH TIME ZONE NOT NULL,
    created_by          NUMBER(19,0)        NOT NULL,
    updated_by          NUMBER(19,0)        NOT NULL,
    version             NUMBER(19,0)        DEFAULT 1 NOT NULL,
    archived_at         TIMESTAMP WITH TIME ZONE,
    archived_by         NUMBER(19,0),
    CONSTRAINT pk_milestone PRIMARY KEY (id),
    CONSTRAINT fk_milestone_project FOREIGN KEY (project_id) REFERENCES project (id),
    CONSTRAINT fk_milestone_stage FOREIGN KEY (stage_id) REFERENCES workflow_stage (id),
    CONSTRAINT ck_milestone_dates CHECK (planned_end_date >= planned_start_date
        AND planned_start_date = TRUNC(planned_start_date) AND planned_end_date = TRUNC(planned_end_date)
        AND (actual_end_date IS NULL OR actual_end_date = TRUNC(actual_end_date))
        AND (forecast_end_date IS NULL OR forecast_end_date = TRUNC(forecast_end_date))),
    CONSTRAINT ck_milestone_progress CHECK (progress_pct BETWEEN 0 AND 100),
    CONSTRAINT ck_milestone_major CHECK (is_major IN (0, 1)),
    CONSTRAINT fk_milestone_created_by FOREIGN KEY (created_by) REFERENCES app_user (id),
    CONSTRAINT fk_milestone_updated_by FOREIGN KEY (updated_by) REFERENCES app_user (id),
    CONSTRAINT fk_milestone_archived_by FOREIGN KEY (archived_by) REFERENCES app_user (id)
);

CREATE SEQUENCE risk_seq START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE TABLE risk (
    id                  NUMBER(19,0)        NOT NULL,
    code                VARCHAR2(20 CHAR)   NOT NULL,
    project_id          NUMBER(19,0)        NOT NULL,
    title_en            VARCHAR2(500 CHAR)  NOT NULL,
    title_ar            VARCHAR2(500 CHAR)  NOT NULL,
    category            VARCHAR2(20 CHAR)   NOT NULL,
    probability         NUMBER(1,0)         NOT NULL,
    impact              NUMBER(1,0)         NOT NULL,
    owner_name          VARCHAR2(160 CHAR),
    mitigation_en       CLOB,
    mitigation_ar       CLOB,
    mitigation_due_date DATE,
    status_code         VARCHAR2(30 CHAR)   NOT NULL,
    created_at          TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at          TIMESTAMP WITH TIME ZONE NOT NULL,
    created_by          NUMBER(19,0)        NOT NULL,
    updated_by          NUMBER(19,0)        NOT NULL,
    version             NUMBER(19,0)        DEFAULT 1 NOT NULL,
    archived_at         TIMESTAMP WITH TIME ZONE,
    archived_by         NUMBER(19,0),
    CONSTRAINT pk_risk PRIMARY KEY (id),
    CONSTRAINT uq_risk_code UNIQUE (code),
    CONSTRAINT ck_risk_code CHECK (REGEXP_LIKE(code, '^[A-Z0-9-]{2,20}$')),
    CONSTRAINT ck_risk_category CHECK (category IN ('TECHNICAL', 'SCHEDULE', 'FINANCIAL', 'SUPPLY_CHAIN', 'COMMERCIAL',
        'OPERATIONAL', 'ENVIRONMENTAL', 'REGULATORY')),
    CONSTRAINT ck_risk_scores CHECK (probability BETWEEN 1 AND 5 AND impact BETWEEN 1 AND 5),
    CONSTRAINT ck_risk_due CHECK (mitigation_due_date IS NULL OR mitigation_due_date = TRUNC(mitigation_due_date)),
    CONSTRAINT ck_risk_texts CHECK ((mitigation_en IS NULL OR LENGTH(mitigation_en) <= 2000)
        AND (mitigation_ar IS NULL OR LENGTH(mitigation_ar) <= 2000)),
    CONSTRAINT fk_risk_project FOREIGN KEY (project_id) REFERENCES project (id),
    CONSTRAINT fk_risk_created_by FOREIGN KEY (created_by) REFERENCES app_user (id),
    CONSTRAINT fk_risk_updated_by FOREIGN KEY (updated_by) REFERENCES app_user (id),
    CONSTRAINT fk_risk_archived_by FOREIGN KEY (archived_by) REFERENCES app_user (id)
);

CREATE SEQUENCE issue_seq START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE TABLE issue (
    id                  NUMBER(19,0)        NOT NULL,
    code                VARCHAR2(20 CHAR)   NOT NULL,
    project_id          NUMBER(19,0)        NOT NULL,
    title_en            VARCHAR2(500 CHAR)  NOT NULL,
    title_ar            VARCHAR2(500 CHAR)  NOT NULL,
    severity            VARCHAR2(10 CHAR)   NOT NULL,
    owner_name          VARCHAR2(160 CHAR),
    raised_date         DATE                NOT NULL,
    target_date         DATE,
    is_escalated        NUMBER(1)           DEFAULT 0 NOT NULL,
    status_code         VARCHAR2(30 CHAR)   NOT NULL,
    resolution_en       CLOB,
    resolution_ar       CLOB,
    created_at          TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at          TIMESTAMP WITH TIME ZONE NOT NULL,
    created_by          NUMBER(19,0)        NOT NULL,
    updated_by          NUMBER(19,0)        NOT NULL,
    version             NUMBER(19,0)        DEFAULT 1 NOT NULL,
    archived_at         TIMESTAMP WITH TIME ZONE,
    archived_by         NUMBER(19,0),
    CONSTRAINT pk_issue PRIMARY KEY (id),
    CONSTRAINT uq_issue_code UNIQUE (code),
    CONSTRAINT ck_issue_code CHECK (REGEXP_LIKE(code, '^[A-Z0-9-]{2,20}$')),
    CONSTRAINT ck_issue_severity CHECK (severity IN ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW')),
    CONSTRAINT ck_issue_dates CHECK (raised_date = TRUNC(raised_date) AND (target_date IS NULL OR target_date = TRUNC(target_date))),
    CONSTRAINT ck_issue_escalated CHECK (is_escalated IN (0, 1)),
    CONSTRAINT ck_issue_texts CHECK ((resolution_en IS NULL OR LENGTH(resolution_en) <= 2000)
        AND (resolution_ar IS NULL OR LENGTH(resolution_ar) <= 2000)),
    CONSTRAINT fk_issue_project FOREIGN KEY (project_id) REFERENCES project (id),
    CONSTRAINT fk_issue_created_by FOREIGN KEY (created_by) REFERENCES app_user (id),
    CONSTRAINT fk_issue_updated_by FOREIGN KEY (updated_by) REFERENCES app_user (id),
    CONSTRAINT fk_issue_archived_by FOREIGN KEY (archived_by) REFERENCES app_user (id)
);

-- ---------------------------------------------------------------- history -----------------------------------------
CREATE SEQUENCE metric_snapshot_seq START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE TABLE metric_snapshot (
    id              NUMBER(19,0)        NOT NULL,
    snapshot_date   DATE                NOT NULL,
    metric          VARCHAR2(60 CHAR)   NOT NULL,
    department_id   NUMBER(19,0),
    category_id     NUMBER(19,0),
    value           NUMBER(16,2)        NOT NULL,
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT pk_metric_snapshot PRIMARY KEY (id),
    CONSTRAINT ck_metric_snapshot_date CHECK (snapshot_date = TRUNC(snapshot_date)),
    CONSTRAINT fk_metric_snapshot_dept FOREIGN KEY (department_id) REFERENCES department (id),
    CONSTRAINT fk_metric_snapshot_cat FOREIGN KEY (category_id) REFERENCES capability_category (id)
);
