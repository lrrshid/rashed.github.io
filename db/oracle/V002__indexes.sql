-- Indexes. Twin: the CREATE INDEX statements of db/sqlite/V001__schema.sql.
CREATE UNIQUE INDEX uq_app_user_username_ci ON app_user (LOWER(username));
CREATE INDEX ix_app_session_user ON app_session (user_id);
CREATE INDEX ix_audit_event_entity ON audit_event (entity_type, entity_id);
CREATE INDEX ix_audit_event_occurred ON audit_event (occurred_at);
CREATE INDEX ix_audit_event_actor ON audit_event (actor_id);
CREATE INDEX ix_saved_view_user ON saved_view (user_id, page);
CREATE INDEX ix_workflow_stage_type ON workflow_stage (project_type_id, sort_order);
CREATE INDEX ix_requirement_dept_cat ON capability_requirement (department_id, category_id);
CREATE INDEX ix_model_category ON capability_model (category_id);
CREATE INDEX ix_requirement_model_model ON requirement_model (model_id);
CREATE INDEX ix_asset_model ON asset (model_id);
CREATE INDEX ix_asset_department ON asset (department_id, status_code);
CREATE INDEX ix_asset_site ON asset (site_id);
-- Unique serial numbers where one is given (NULLs are not indexed in Oracle).
CREATE UNIQUE INDEX uq_asset_serial ON asset (serial_number);
CREATE INDEX ix_asset_status_history_asset ON asset_status_history (asset_id, changed_at);
CREATE INDEX ix_project_department ON project (department_id, status_code);
CREATE INDEX ix_project_type ON project (project_type_id);
CREATE INDEX ix_project_requirement_req ON project_requirement (requirement_id);
CREATE INDEX ix_project_model_model ON project_model (model_id);
CREATE INDEX ix_milestone_project ON milestone (project_id, sort_order);
CREATE INDEX ix_risk_project ON risk (project_id);
CREATE INDEX ix_issue_project ON issue (project_id);
CREATE INDEX ix_metric_snapshot ON metric_snapshot (metric, snapshot_date);
