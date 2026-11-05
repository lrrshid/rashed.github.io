-- Custom report templates, scheduled reports and the report run log. Twin of db/sqlite/V004__reports.sql.

CREATE SEQUENCE report_template_seq START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE TABLE report_template (
    id              NUMBER(19,0)        NOT NULL,
    name            VARCHAR2(120 CHAR)  NOT NULL,
    owner_id        NUMBER(19,0)        NOT NULL,
    is_shared       NUMBER(1)           DEFAULT 0 NOT NULL,
    definition_json CLOB                NOT NULL,
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at      TIMESTAMP WITH TIME ZONE NOT NULL,
    created_by      NUMBER(19,0)        NOT NULL,
    updated_by      NUMBER(19,0)        NOT NULL,
    version         NUMBER(19,0)        DEFAULT 1 NOT NULL,
    archived_at     TIMESTAMP WITH TIME ZONE,
    archived_by     NUMBER(19,0),
    CONSTRAINT pk_report_template PRIMARY KEY (id),
    CONSTRAINT ck_report_template_shared CHECK (is_shared IN (0, 1)),
    CONSTRAINT ck_report_template_def CHECK (LENGTH(definition_json) <= 4000),
    CONSTRAINT fk_report_template_owner FOREIGN KEY (owner_id) REFERENCES app_user (id),
    CONSTRAINT fk_report_template_cby FOREIGN KEY (created_by) REFERENCES app_user (id),
    CONSTRAINT fk_report_template_uby FOREIGN KEY (updated_by) REFERENCES app_user (id),
    CONSTRAINT fk_report_template_aby FOREIGN KEY (archived_by) REFERENCES app_user (id)
);

CREATE SEQUENCE report_schedule_seq START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE TABLE report_schedule (
    id              NUMBER(19,0)        NOT NULL,
    name            VARCHAR2(120 CHAR)  NOT NULL,
    report_key      VARCHAR2(80 CHAR),
    template_id     NUMBER(19,0),
    frequency       VARCHAR2(10 CHAR)   NOT NULL,
    language        VARCHAR2(10 CHAR)   NOT NULL,
    file_format     VARCHAR2(10 CHAR)   NOT NULL,
    send_time       VARCHAR2(5 CHAR)    NOT NULL,
    recipients      VARCHAR2(1000 CHAR) NOT NULL,
    next_run_date   DATE                NOT NULL,
    is_active       NUMBER(1)           DEFAULT 1 NOT NULL,
    owner_id        NUMBER(19,0)        NOT NULL,
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at      TIMESTAMP WITH TIME ZONE NOT NULL,
    created_by      NUMBER(19,0)        NOT NULL,
    updated_by      NUMBER(19,0)        NOT NULL,
    version         NUMBER(19,0)        DEFAULT 1 NOT NULL,
    CONSTRAINT pk_report_schedule PRIMARY KEY (id),
    CONSTRAINT ck_report_schedule_target CHECK (report_key IS NOT NULL OR template_id IS NOT NULL),
    CONSTRAINT ck_report_schedule_freq CHECK (frequency IN ('DAILY', 'WEEKLY', 'MONTHLY', 'QUARTERLY')),
    CONSTRAINT ck_report_schedule_lang CHECK (language IN ('EN', 'AR', 'BILINGUAL')),
    CONSTRAINT ck_report_schedule_format CHECK (file_format IN ('XLSX', 'CSV', 'PPTX', 'HTML')),
    CONSTRAINT ck_report_schedule_time CHECK (REGEXP_LIKE(send_time, '^[0-2][0-9]:[0-5][0-9]$')),
    CONSTRAINT ck_report_schedule_date CHECK (next_run_date = TRUNC(next_run_date)),
    CONSTRAINT ck_report_schedule_active CHECK (is_active IN (0, 1)),
    CONSTRAINT fk_report_schedule_template FOREIGN KEY (template_id) REFERENCES report_template (id),
    CONSTRAINT fk_report_schedule_owner FOREIGN KEY (owner_id) REFERENCES app_user (id),
    CONSTRAINT fk_report_schedule_cby FOREIGN KEY (created_by) REFERENCES app_user (id),
    CONSTRAINT fk_report_schedule_uby FOREIGN KEY (updated_by) REFERENCES app_user (id)
);

CREATE SEQUENCE report_run_seq START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE TABLE report_run (
    id              NUMBER(19,0)        NOT NULL,
    report_key      VARCHAR2(80 CHAR)   NOT NULL,
    title           VARCHAR2(200 CHAR)  NOT NULL,
    schedule_id     NUMBER(19,0),
    run_at          TIMESTAMP WITH TIME ZONE NOT NULL,
    run_by          NUMBER(19,0)        NOT NULL,
    language        VARCHAR2(10 CHAR)   NOT NULL,
    file_format     VARCHAR2(10 CHAR)   NOT NULL,
    row_count       NUMBER(10,0)        DEFAULT 0 NOT NULL,
    file_name       VARCHAR2(200 CHAR),
    CONSTRAINT pk_report_run PRIMARY KEY (id),
    CONSTRAINT ck_report_run_lang CHECK (language IN ('EN', 'AR', 'BILINGUAL')),
    CONSTRAINT ck_report_run_format CHECK (file_format IN ('SCREEN', 'XLSX', 'CSV', 'PPTX', 'HTML', 'PRINT')),
    CONSTRAINT fk_report_run_schedule FOREIGN KEY (schedule_id) REFERENCES report_schedule (id),
    CONSTRAINT fk_report_run_by FOREIGN KEY (run_by) REFERENCES app_user (id)
);
CREATE INDEX ix_report_run_at ON report_run (run_at);
