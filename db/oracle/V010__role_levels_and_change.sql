-- The organisation's role structure (owner, 25 Nov 2026). Each role has a level in the hierarchy (APP_ROLE.tier: 1 at
-- the top, 0 = not placed), shown in Settings > Roles. The new permission records.change separates changing,
-- archiving and restoring records from adding them: a role with edit.* but without records.change adds records and
-- views them, nothing more. Every role that holds an edit.* permission is given records.change here, so the roles of
-- an existing schema keep doing what they did. Twin of db/sqlite/V008__role_levels_and_change.sql.
-- No new table, so no new runtime grant (CPC_APP already has SELECT, INSERT, UPDATE on app_role and role_permission).

ALTER TABLE app_role ADD (tier NUMBER(2,0) DEFAULT 0 NOT NULL);
ALTER TABLE app_role ADD CONSTRAINT ck_app_role_tier CHECK (tier BETWEEN 0 AND 20);

ALTER TABLE role_permission DROP CONSTRAINT ck_role_permission;
ALTER TABLE role_permission ADD CONSTRAINT ck_role_permission CHECK (permission IN ('view', 'edit.requirements',
    'edit.models', 'edit.assets', 'edit.projects', 'edit.risks', 'edit.maintenance', 'edit.testing', 'edit.documents',
    'records.change', 'reports.view', 'reports.exec', 'reports.build', 'reports.schedule', 'export', 'admin'));

INSERT INTO role_permission (role_id, permission, created_at)
    SELECT DISTINCT role_id, 'records.change', SYSTIMESTAMP FROM role_permission WHERE permission LIKE 'edit.%';
COMMIT;
