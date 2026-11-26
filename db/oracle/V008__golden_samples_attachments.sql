-- Golden-sample trials, the reason a capability entered maintenance, and the new kinds of attached scans
-- (trial, higher-level directive letter, official trial form, investigation board, capability deed, live
-- demonstration report, and the culture library: references, user guides, acquisition plans).
-- Twin of db/sqlite/V006__golden_samples_attachments.sql. Runtime grants: docs/oracle-migration.md section 3.

CREATE SEQUENCE golden_sample_trial_seq START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE TABLE golden_sample_trial (
    id              NUMBER(19,0)        NOT NULL,
    code            VARCHAR2(20 CHAR)   NOT NULL,
    title_en        VARCHAR2(200 CHAR)  NOT NULL,
    title_ar        VARCHAR2(200 CHAR)  NOT NULL,
    model_id        NUMBER(19,0)        NOT NULL,
    trial_date      DATE                NOT NULL,
    status_code     VARCHAR2(30 CHAR)   NOT NULL,
    notes_en        CLOB,
    notes_ar        CLOB,
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at      TIMESTAMP WITH TIME ZONE NOT NULL,
    created_by      NUMBER(19,0)        NOT NULL,
    updated_by      NUMBER(19,0)        NOT NULL,
    version         NUMBER(19,0)        DEFAULT 1 NOT NULL,
    archived_at     TIMESTAMP WITH TIME ZONE,
    archived_by     NUMBER(19,0),
    CONSTRAINT pk_golden_sample_trial PRIMARY KEY (id),
    CONSTRAINT uq_golden_sample_trial_code UNIQUE (code),
    CONSTRAINT ck_golden_sample_trial_code CHECK (REGEXP_LIKE(code, '^[A-Z0-9-]{2,20}$')),
    CONSTRAINT ck_golden_sample_trial_date CHECK (trial_date = TRUNC(trial_date)),
    CONSTRAINT ck_golden_sample_trial_texts CHECK ((notes_en IS NULL OR LENGTH(notes_en) <= 2000)
        AND (notes_ar IS NULL OR LENGTH(notes_ar) <= 2000)),
    CONSTRAINT fk_golden_sample_trial_model FOREIGN KEY (model_id) REFERENCES capability_model (id),
    CONSTRAINT fk_golden_trial_created_by FOREIGN KEY (created_by) REFERENCES app_user (id),
    CONSTRAINT fk_golden_trial_updated_by FOREIGN KEY (updated_by) REFERENCES app_user (id),
    CONSTRAINT fk_golden_trial_archived_by FOREIGN KEY (archived_by) REFERENCES app_user (id)
);
CREATE INDEX ix_golden_sample_trial_model ON golden_sample_trial (model_id, trial_date);

ALTER TABLE maintenance_order ADD (entry_reason_en CLOB);
ALTER TABLE maintenance_order ADD (entry_reason_ar CLOB);
ALTER TABLE maintenance_order ADD CONSTRAINT ck_maintenance_order_reason CHECK (
    (entry_reason_en IS NULL OR LENGTH(entry_reason_en) <= 2000) AND (entry_reason_ar IS NULL OR LENGTH(entry_reason_ar) <= 2000));

ALTER TABLE document DROP CONSTRAINT ck_document_type;
ALTER TABLE document ADD CONSTRAINT ck_document_type CHECK (doc_type IN ('REPORT', 'SPECIFICATION', 'CONTRACT',
    'TEST_REPORT', 'MANUAL', 'CERTIFICATE', 'CORRESPONDENCE', 'PRESENTATION', 'DATASHEET', 'OTHER',
    'GOLDEN_TRIAL', 'DIRECTIVE_LETTER', 'OFFICIAL_TRIAL_FORM', 'INVESTIGATION', 'CAPABILITY_DEED',
    'LIVE_DEMO_REPORT', 'REFERENCE', 'USER_GUIDE', 'ACQUISITION_PLAN'));
ALTER TABLE document DROP CONSTRAINT ck_document_entity;
ALTER TABLE document ADD CONSTRAINT ck_document_entity CHECK (entity_type IN ('CAPABILITY_MODEL', 'ASSET', 'PROJECT',
    'TEST_EVENT', 'MAINTENANCE_ORDER', 'ORGANIZATION', 'CONTRACT', 'CAPABILITY_REQUIREMENT',
    'GOLDEN_SAMPLE_TRIAL', 'LIBRARY'));
