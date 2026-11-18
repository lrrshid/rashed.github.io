-- Organisational units that conduct tests: a directorate and its sections (two levels), and the conducting unit of
-- each test. Twin of db/sqlite/V005__org_units.sql.

CREATE SEQUENCE org_unit_seq START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE TABLE org_unit (
    id              NUMBER(19,0)        NOT NULL,
    code            VARCHAR2(20 CHAR)   NOT NULL,
    name_en         VARCHAR2(200 CHAR)  NOT NULL,
    name_ar         VARCHAR2(200 CHAR)  NOT NULL,
    parent_id       NUMBER(19,0),
    sort_order      NUMBER(10,0)        DEFAULT 0 NOT NULL,
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at      TIMESTAMP WITH TIME ZONE NOT NULL,
    created_by      NUMBER(19,0)        NOT NULL,
    updated_by      NUMBER(19,0)        NOT NULL,
    version         NUMBER(19,0)        DEFAULT 1 NOT NULL,
    archived_at     TIMESTAMP WITH TIME ZONE,
    archived_by     NUMBER(19,0),
    CONSTRAINT pk_org_unit PRIMARY KEY (id),
    CONSTRAINT uq_org_unit_code UNIQUE (code),
    CONSTRAINT ck_org_unit_code CHECK (REGEXP_LIKE(code, '^[A-Z0-9_-]{1,20}$')),
    CONSTRAINT ck_org_unit_parent CHECK (parent_id IS NULL OR parent_id <> id),
    CONSTRAINT fk_org_unit_parent FOREIGN KEY (parent_id) REFERENCES org_unit (id),
    CONSTRAINT fk_org_unit_created_by FOREIGN KEY (created_by) REFERENCES app_user (id),
    CONSTRAINT fk_org_unit_updated_by FOREIGN KEY (updated_by) REFERENCES app_user (id),
    CONSTRAINT fk_org_unit_archived_by FOREIGN KEY (archived_by) REFERENCES app_user (id)
);
CREATE INDEX ix_org_unit_parent ON org_unit (parent_id);

ALTER TABLE test_event ADD (unit_id NUMBER(19,0));
ALTER TABLE test_event ADD CONSTRAINT fk_test_event_unit FOREIGN KEY (unit_id) REFERENCES org_unit (id);
CREATE INDEX ix_test_event_unit ON test_event (unit_id);
