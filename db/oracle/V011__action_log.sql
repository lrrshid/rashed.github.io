-- User tracking «تتبع المستخدمين» (owner, 25 Nov 2026: the commander sees everything people do in the system). ACTION_LOG
-- holds every action a person takes, whether it was carried out or refused, with the time, the record, the reason it
-- failed and the device: sign-ins (failed ones too) and sign-outs, every change asked for (add, change, archive,
-- restore, upload, import, settings), opening a record or a report, downloads and exports. Request values are never
-- kept (no passwords, no texts typed), only what identifies the action. Append-only, like AUDIT_EVENT.
-- The permission tracking.view opens the screen; every role holding admin is given it here (they saw the user board
-- it replaces). Twin of db/sqlite/V009__action_log.sql. Runtime grant: SELECT, INSERT ON action_log
-- (db/oracle/runtime-grants.sql).

CREATE SEQUENCE action_log_seq START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE TABLE action_log (
    id              NUMBER(19,0)        NOT NULL,
    occurred_at     TIMESTAMP WITH TIME ZONE NOT NULL,
    user_id         NUMBER(19,0),
    username        VARCHAR2(120 CHAR)  NOT NULL,
    display_name    VARCHAR2(160 CHAR),
    role_code       VARCHAR2(30 CHAR),
    action          VARCHAR2(30 CHAR)   NOT NULL,
    entity_type     VARCHAR2(40 CHAR),
    entity_id       NUMBER(19,0),
    record_code     VARCHAR2(120 CHAR),
    record_name_en  VARCHAR2(200 CHAR),
    record_name_ar  VARCHAR2(200 CHAR),
    outcome         VARCHAR2(10 CHAR)   NOT NULL,
    http_status     NUMBER(3,0)         NOT NULL,
    error_code      VARCHAR2(40 CHAR),
    error_message   VARCHAR2(300 CHAR),
    error_fields    VARCHAR2(300 CHAR),
    detail          VARCHAR2(300 CHAR),
    audit_event_id  NUMBER(19,0),
    changes_count   NUMBER(10,0)        DEFAULT 0 NOT NULL,
    method          VARCHAR2(10 CHAR)   NOT NULL,
    path            VARCHAR2(300 CHAR)  NOT NULL,
    client_ip       VARCHAR2(64 CHAR),
    request_id      VARCHAR2(64 CHAR),
    preview_role    VARCHAR2(30 CHAR),
    CONSTRAINT pk_action_log PRIMARY KEY (id),
    CONSTRAINT fk_action_log_user FOREIGN KEY (user_id) REFERENCES app_user (id),
    CONSTRAINT fk_action_log_audit FOREIGN KEY (audit_event_id) REFERENCES audit_event (id),
    CONSTRAINT ck_action_log_action CHECK (REGEXP_LIKE(action, '^[A-Z_]{2,30}$')),
    CONSTRAINT ck_action_log_type CHECK (entity_type IS NULL OR REGEXP_LIKE(entity_type, '^[A-Z_]{2,40}$')),
    CONSTRAINT ck_action_log_outcome CHECK (outcome IN ('DONE', 'FAILED')),
    CONSTRAINT ck_action_log_status CHECK (http_status BETWEEN 100 AND 599),
    CONSTRAINT ck_action_log_method CHECK (method IN ('GET', 'POST', 'PUT', 'PATCH', 'DELETE')),
    CONSTRAINT ck_action_log_changes CHECK (changes_count >= 0)
);
CREATE INDEX ix_action_log_occurred ON action_log (occurred_at);
CREATE INDEX ix_action_log_user ON action_log (user_id, occurred_at);
CREATE INDEX ix_action_log_outcome ON action_log (outcome, occurred_at);

-- What happened stays as it happened: the database refuses updates and deletes, whoever asks.
CREATE OR REPLACE TRIGGER trg_action_log_append_only
    BEFORE UPDATE OR DELETE ON action_log
BEGIN
    RAISE_APPLICATION_ERROR(-20002, 'ACTION_LOG is append-only');
END;
/

ALTER TABLE role_permission DROP CONSTRAINT ck_role_permission;
ALTER TABLE role_permission ADD CONSTRAINT ck_role_permission CHECK (permission IN ('view', 'edit.requirements',
    'edit.models', 'edit.assets', 'edit.projects', 'edit.risks', 'edit.maintenance', 'edit.testing', 'edit.documents',
    'records.change', 'reports.view', 'reports.exec', 'reports.build', 'reports.schedule', 'export', 'tracking.view',
    'admin'));

INSERT INTO role_permission (role_id, permission, created_at)
    SELECT DISTINCT role_id, 'tracking.view', SYSTIMESTAMP FROM role_permission WHERE permission = 'admin';
COMMIT;
