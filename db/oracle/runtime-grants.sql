-- The runtime account's grants: run as the schema owner after the V0xx scripts (docs/oracle-migration.md 3).
-- The runtime account is called CPC_APP here; if yours has another name, change it in every line first.
-- Business records are never deleted (they are archived), so the runtime account gets no DELETE on them.
-- This file is also what Settings > Database checks a new database against (services/connections/
-- database_provider.py), and what the Oracle tests grant (backend/tests/oracle). Keep it complete: a new table
-- gets its line here in the same change as its V0xx script.

-- every business and list table: read, add, change
GRANT SELECT, INSERT, UPDATE ON app_role TO CPC_APP;
GRANT SELECT, INSERT, UPDATE ON app_user TO CPC_APP;
GRANT SELECT, INSERT, UPDATE, DELETE ON role_permission TO CPC_APP;   -- a role's permission list is edited
GRANT SELECT, INSERT, UPDATE, DELETE ON user_department TO CPC_APP;   -- a user's departments are edited
GRANT SELECT, INSERT, UPDATE, DELETE ON app_session TO CPC_APP;       -- sign-out and expiry delete sessions
GRANT SELECT, INSERT ON audit_event TO CPC_APP;                       -- append-only
GRANT SELECT, INSERT ON action_log TO CPC_APP;                        -- append-only (user tracking, V011)
GRANT SELECT, INSERT, UPDATE ON app_setting TO CPC_APP;
GRANT SELECT, INSERT, DELETE ON saved_view TO CPC_APP;                -- personal views are deleted by their owner
GRANT SELECT, INSERT, UPDATE ON department TO CPC_APP;
GRANT SELECT, INSERT, UPDATE ON capability_category TO CPC_APP;
GRANT SELECT, INSERT, UPDATE ON site TO CPC_APP;
GRANT SELECT, INSERT, UPDATE ON organization TO CPC_APP;
GRANT SELECT, INSERT, UPDATE ON status_def TO CPC_APP;
GRANT SELECT, INSERT, UPDATE ON project_type TO CPC_APP;
GRANT SELECT, INSERT, UPDATE ON workflow_stage TO CPC_APP;
GRANT SELECT, INSERT, UPDATE ON spec_field TO CPC_APP;
GRANT SELECT, INSERT, UPDATE ON capability_requirement TO CPC_APP;
GRANT SELECT, INSERT, UPDATE, DELETE ON requirement_model TO CPC_APP; -- link rows
GRANT SELECT, INSERT, UPDATE ON capability_model TO CPC_APP;
GRANT SELECT, INSERT, UPDATE ON contract TO CPC_APP;
GRANT SELECT, INSERT, UPDATE ON asset TO CPC_APP;
GRANT SELECT, INSERT ON asset_status_history TO CPC_APP;
GRANT SELECT, INSERT, UPDATE ON project TO CPC_APP;
GRANT SELECT, INSERT, UPDATE, DELETE ON project_requirement TO CPC_APP; -- link rows
GRANT SELECT, INSERT, UPDATE, DELETE ON project_model TO CPC_APP;       -- link rows
GRANT SELECT, INSERT, UPDATE ON project_health_note TO CPC_APP;
GRANT SELECT, INSERT, UPDATE ON milestone TO CPC_APP;
GRANT SELECT, INSERT, UPDATE ON risk TO CPC_APP;
GRANT SELECT, INSERT, UPDATE ON issue TO CPC_APP;
GRANT SELECT, INSERT, DELETE ON metric_snapshot TO CPC_APP;           -- today's snapshot is replaced
-- V004
GRANT SELECT, INSERT, UPDATE ON test_event TO CPC_APP;
GRANT SELECT, INSERT, UPDATE ON maintenance_order TO CPC_APP;
GRANT SELECT, INSERT, UPDATE ON ai_technology TO CPC_APP;
GRANT SELECT, INSERT, DELETE ON model_ai_tech TO CPC_APP;              -- a model's AI functions are edited
GRANT SELECT, INSERT, UPDATE ON ai_level_criterion TO CPC_APP;
GRANT SELECT, INSERT, UPDATE ON development_opportunity TO CPC_APP;
-- V005
GRANT SELECT, INSERT, UPDATE ON document TO CPC_APP;
GRANT SELECT, INSERT ON document_version TO CPC_APP;                 -- append-only
GRANT SELECT, INSERT, UPDATE ON alert_rule TO CPC_APP;
GRANT SELECT, INSERT ON alert_ack TO CPC_APP;
-- V006
GRANT SELECT, INSERT, UPDATE ON report_template TO CPC_APP;
GRANT SELECT, INSERT, UPDATE ON report_schedule TO CPC_APP;
GRANT SELECT, INSERT ON report_run TO CPC_APP;
-- V007
GRANT SELECT, INSERT, UPDATE ON org_unit TO CPC_APP;
-- V008
GRANT SELECT, INSERT, UPDATE ON golden_sample_trial TO CPC_APP;
-- V009 (Settings > connections)
GRANT SELECT, INSERT, UPDATE ON setting_profile TO CPC_APP;
GRANT SELECT, INSERT, UPDATE ON setting_revision TO CPC_APP;
GRANT SELECT, INSERT ON setting_test TO CPC_APP;                      -- test results are only added
GRANT SELECT, INSERT, UPDATE ON setting_cert TO CPC_APP;
GRANT SELECT, INSERT, UPDATE ON egress_rule TO CPC_APP;
GRANT SELECT, INSERT, UPDATE ON connection_setting TO CPC_APP;
GRANT SELECT, INSERT, UPDATE, DELETE ON process_heartbeat TO CPC_APP; -- rows of stopped processes are pruned
-- every sequence
BEGIN
  FOR s IN (SELECT sequence_name FROM user_sequences) LOOP
    EXECUTE IMMEDIATE 'GRANT SELECT ON ' || s.sequence_name || ' TO CPC_APP';
  END LOOP;
END;
/
