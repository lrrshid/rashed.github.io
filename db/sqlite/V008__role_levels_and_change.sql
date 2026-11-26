-- migrate: foreign-keys-off
-- The organisation's role structure (owner, 25 Nov 2026). Each role has a level in the hierarchy (APP_ROLE.tier: 1 at
-- the top, 0 = not placed), shown in Settings > Roles. The new permission records.change separates changing,
-- archiving and restoring records from adding them: a role with edit.* but without records.change adds records and
-- views them, nothing more. Every role that holds an edit.* permission is given records.change here, so the roles of
-- an existing database keep doing what they did. Twin of db/oracle/V010__role_levels_and_change.sql.

ALTER TABLE APP_ROLE ADD COLUMN tier INTEGER NOT NULL DEFAULT 0 CHECK (tier BETWEEN 0 AND 20);

-- SQLite cannot change a CHECK constraint in place: ROLE_PERMISSION is rebuilt with the wider list (same columns, same
-- rows).
CREATE TABLE ROLE_PERMISSION_NEW (
    role_id         INTEGER NOT NULL REFERENCES APP_ROLE (id),
    permission      TEXT    NOT NULL CHECK (permission IN ('view', 'edit.requirements', 'edit.models', 'edit.assets',
                        'edit.projects', 'edit.risks', 'edit.maintenance', 'edit.testing', 'edit.documents',
                        'records.change', 'reports.view', 'reports.exec', 'reports.build', 'reports.schedule', 'export',
                        'admin')),
    created_at      TEXT    NOT NULL,
    PRIMARY KEY (role_id, permission)
);
INSERT INTO ROLE_PERMISSION_NEW (role_id, permission, created_at)
    SELECT role_id, permission, created_at FROM ROLE_PERMISSION;
DROP TABLE ROLE_PERMISSION;
ALTER TABLE ROLE_PERMISSION_NEW RENAME TO ROLE_PERMISSION;

INSERT INTO ROLE_PERMISSION (role_id, permission, created_at)
    SELECT DISTINCT role_id, 'records.change', strftime('%Y-%m-%d %H:%M:%S', 'now') || '.000000'
    FROM ROLE_PERMISSION WHERE permission LIKE 'edit.%';
