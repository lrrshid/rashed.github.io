-- Versioned documents, alert routing rules and acknowledgements.
-- Twin of db/sqlite/V003__documents_alerts.sql. Runtime grants: docs/oracle-migration.md section 3.

CREATE SEQUENCE document_seq START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE TABLE document (
    id              NUMBER(19,0)        NOT NULL,
    code            VARCHAR2(20 CHAR)   NOT NULL,
    title_en        VARCHAR2(200 CHAR)  NOT NULL,
    title_ar        VARCHAR2(200 CHAR)  NOT NULL,
    doc_type        VARCHAR2(20 CHAR)   NOT NULL,
    entity_type     VARCHAR2(30 CHAR)   NOT NULL,
    entity_id       NUMBER(19,0)        NOT NULL,
    department_id   NUMBER(19,0),
    current_version NUMBER(10,0)        DEFAULT 0 NOT NULL,
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at      TIMESTAMP WITH TIME ZONE NOT NULL,
    created_by      NUMBER(19,0)        NOT NULL,
    updated_by      NUMBER(19,0)        NOT NULL,
    version         NUMBER(19,0)        DEFAULT 1 NOT NULL,
    archived_at     TIMESTAMP WITH TIME ZONE,
    archived_by     NUMBER(19,0),
    CONSTRAINT pk_document PRIMARY KEY (id),
    CONSTRAINT uq_document_code UNIQUE (code),
    CONSTRAINT ck_document_code CHECK (REGEXP_LIKE(code, '^[A-Z0-9-]{2,20}$')),
    CONSTRAINT ck_document_type CHECK (doc_type IN ('REPORT', 'SPECIFICATION', 'CONTRACT', 'TEST_REPORT', 'MANUAL',
        'CERTIFICATE', 'CORRESPONDENCE', 'PRESENTATION', 'DATASHEET', 'OTHER')),
    CONSTRAINT ck_document_entity CHECK (entity_type IN ('CAPABILITY_MODEL', 'ASSET', 'PROJECT', 'TEST_EVENT',
        'MAINTENANCE_ORDER', 'ORGANIZATION', 'CONTRACT', 'CAPABILITY_REQUIREMENT')),
    CONSTRAINT ck_document_current CHECK (current_version >= 0),
    CONSTRAINT fk_document_department FOREIGN KEY (department_id) REFERENCES department (id),
    CONSTRAINT fk_document_created_by FOREIGN KEY (created_by) REFERENCES app_user (id),
    CONSTRAINT fk_document_updated_by FOREIGN KEY (updated_by) REFERENCES app_user (id),
    CONSTRAINT fk_document_archived_by FOREIGN KEY (archived_by) REFERENCES app_user (id)
);
CREATE INDEX ix_document_entity ON document (entity_type, entity_id);

CREATE SEQUENCE document_version_seq START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE TABLE document_version (
    id              NUMBER(19,0)        NOT NULL,
    document_id     NUMBER(19,0)        NOT NULL,
    version_no      NUMBER(10,0)        NOT NULL,
    file_name       VARCHAR2(200 CHAR)  NOT NULL,
    content_type    VARCHAR2(120 CHAR)  NOT NULL,
    size_bytes      NUMBER(10,0)        NOT NULL,
    sha256          VARCHAR2(64 CHAR)   NOT NULL,
    note            VARCHAR2(500 CHAR),
    uploaded_at     TIMESTAMP WITH TIME ZONE NOT NULL,
    uploaded_by     NUMBER(19,0)        NOT NULL,
    CONSTRAINT pk_document_version PRIMARY KEY (id),
    CONSTRAINT uq_document_version UNIQUE (document_id, version_no),
    CONSTRAINT fk_document_version_doc FOREIGN KEY (document_id) REFERENCES document (id),
    CONSTRAINT fk_document_version_by FOREIGN KEY (uploaded_by) REFERENCES app_user (id),
    CONSTRAINT ck_document_version_no CHECK (version_no >= 1),
    CONSTRAINT ck_document_version_size CHECK (size_bytes BETWEEN 1 AND 52428800),
    CONSTRAINT ck_document_version_sha CHECK (LENGTH(sha256) = 64)
);

CREATE OR REPLACE TRIGGER trg_document_version_append_only
    BEFORE UPDATE OR DELETE ON document_version
BEGIN
    RAISE_APPLICATION_ERROR(-20002, 'DOCUMENT_VERSION is append-only');
END;
/

CREATE SEQUENCE alert_rule_seq START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE TABLE alert_rule (
    id              NUMBER(19,0)        NOT NULL,
    alert_type      VARCHAR2(40 CHAR)   NOT NULL,
    role_codes      VARCHAR2(500 CHAR)  NOT NULL,
    is_enabled      NUMBER(1)           DEFAULT 1 NOT NULL,
    days_ahead      NUMBER(5,0),
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at      TIMESTAMP WITH TIME ZONE NOT NULL,
    created_by      NUMBER(19,0)        NOT NULL,
    updated_by      NUMBER(19,0)        NOT NULL,
    version         NUMBER(19,0)        DEFAULT 1 NOT NULL,
    CONSTRAINT pk_alert_rule PRIMARY KEY (id),
    CONSTRAINT uq_alert_rule_type UNIQUE (alert_type),
    CONSTRAINT ck_alert_rule_type CHECK (REGEXP_LIKE(alert_type, '^[A-Z_]{2,40}$')),
    CONSTRAINT ck_alert_rule_enabled CHECK (is_enabled IN (0, 1)),
    CONSTRAINT ck_alert_rule_days CHECK (days_ahead IS NULL OR days_ahead BETWEEN 0 AND 3650),
    CONSTRAINT fk_alert_rule_created_by FOREIGN KEY (created_by) REFERENCES app_user (id),
    CONSTRAINT fk_alert_rule_updated_by FOREIGN KEY (updated_by) REFERENCES app_user (id)
);

CREATE TABLE alert_ack (
    alert_key       VARCHAR2(120 CHAR)  NOT NULL,
    user_id         NUMBER(19,0)        NOT NULL,
    acked_at        TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT pk_alert_ack PRIMARY KEY (alert_key, user_id),
    CONSTRAINT fk_alert_ack_user FOREIGN KEY (user_id) REFERENCES app_user (id)
);
