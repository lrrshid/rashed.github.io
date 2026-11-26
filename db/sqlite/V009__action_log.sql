-- migrate: foreign-keys-off
-- User tracking «تتبع المستخدمين» (owner, 25 Nov 2026: the commander sees everything people do in the system). ACTION_LOG
-- holds every action a person takes, whether it was carried out or refused, with the time, the record, the reason it
-- failed and the device: sign-ins (failed ones too) and sign-outs, every change asked for (add, change, archive,
-- restore, upload, import, settings), opening a record or a report, downloads and exports. Request values are never
-- kept (no passwords, no texts typed), only what identifies the action. Append-only, like AUDIT_EVENT.
-- The permission tracking.view opens the screen; every role holding admin is given it here (they saw the user board
-- it replaces). Twin of db/oracle/V011__action_log.sql.

CREATE TABLE ACTION_LOG (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    occurred_at     TEXT    NOT NULL,
    user_id         INTEGER REFERENCES APP_USER (id),
    username        TEXT    NOT NULL CHECK (length(username) BETWEEN 1 AND 120),
    display_name    TEXT    CHECK (display_name IS NULL OR length(display_name) <= 160),
    role_code       TEXT    CHECK (role_code IS NULL OR length(role_code) <= 30),
    action          TEXT    NOT NULL CHECK (length(action) BETWEEN 2 AND 30 AND action NOT GLOB '*[^A-Z_]*'),
    entity_type     TEXT    CHECK (entity_type IS NULL OR (length(entity_type) BETWEEN 2 AND 40
                        AND entity_type NOT GLOB '*[^A-Z_]*')),
    entity_id       INTEGER,
    record_code     TEXT    CHECK (record_code IS NULL OR length(record_code) <= 120),
    record_name_en  TEXT    CHECK (record_name_en IS NULL OR length(record_name_en) <= 200),
    record_name_ar  TEXT    CHECK (record_name_ar IS NULL OR length(record_name_ar) <= 200),
    outcome         TEXT    NOT NULL CHECK (outcome IN ('DONE', 'FAILED')),
    http_status     INTEGER NOT NULL CHECK (http_status BETWEEN 100 AND 599),
    error_code      TEXT    CHECK (error_code IS NULL OR length(error_code) <= 40),
    error_message   TEXT    CHECK (error_message IS NULL OR length(error_message) <= 300),
    error_fields    TEXT    CHECK (error_fields IS NULL OR length(error_fields) <= 300),
    detail          TEXT    CHECK (detail IS NULL OR length(detail) <= 300),
    audit_event_id  INTEGER REFERENCES AUDIT_EVENT (id),
    changes_count   INTEGER NOT NULL DEFAULT 0 CHECK (changes_count >= 0),
    method          TEXT    NOT NULL CHECK (method IN ('GET', 'POST', 'PUT', 'PATCH', 'DELETE')),
    path            TEXT    NOT NULL CHECK (length(path) BETWEEN 1 AND 300),
    client_ip       TEXT    CHECK (client_ip IS NULL OR length(client_ip) <= 64),
    request_id      TEXT    CHECK (request_id IS NULL OR length(request_id) <= 64),
    preview_role    TEXT    CHECK (preview_role IS NULL OR length(preview_role) <= 30)
);
CREATE INDEX ix_action_log_occurred ON ACTION_LOG (occurred_at);
CREATE INDEX ix_action_log_user ON ACTION_LOG (user_id, occurred_at);
CREATE INDEX ix_action_log_outcome ON ACTION_LOG (outcome, occurred_at);

-- What happened stays as it happened: the database refuses updates and deletes.
CREATE TRIGGER trg_action_log_no_update BEFORE UPDATE ON ACTION_LOG
BEGIN
    SELECT RAISE(ABORT, 'ACTION_LOG is append-only');
END;
CREATE TRIGGER trg_action_log_no_delete BEFORE DELETE ON ACTION_LOG
BEGIN
    SELECT RAISE(ABORT, 'ACTION_LOG is append-only');
END;

-- SQLite cannot change a CHECK constraint in place: ROLE_PERMISSION is rebuilt with tracking.view in its list.
CREATE TABLE ROLE_PERMISSION_NEW (
    role_id         INTEGER NOT NULL REFERENCES APP_ROLE (id),
    permission      TEXT    NOT NULL CHECK (permission IN ('view', 'edit.requirements', 'edit.models', 'edit.assets',
                        'edit.projects', 'edit.risks', 'edit.maintenance', 'edit.testing', 'edit.documents',
                        'records.change', 'reports.view', 'reports.exec', 'reports.build', 'reports.schedule', 'export',
                        'tracking.view', 'admin')),
    created_at      TEXT    NOT NULL,
    PRIMARY KEY (role_id, permission)
);
INSERT INTO ROLE_PERMISSION_NEW (role_id, permission, created_at)
    SELECT role_id, permission, created_at FROM ROLE_PERMISSION;
DROP TABLE ROLE_PERMISSION;
ALTER TABLE ROLE_PERMISSION_NEW RENAME TO ROLE_PERMISSION;

INSERT INTO ROLE_PERMISSION (role_id, permission, created_at)
    SELECT DISTINCT role_id, 'tracking.view', strftime('%Y-%m-%d %H:%M:%S', 'now') || '.000000'
    FROM ROLE_PERMISSION WHERE permission = 'admin';
