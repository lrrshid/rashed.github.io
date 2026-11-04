-- Audit rows are append-only: the database refuses updates and deletes, whoever asks.
-- Twin: the trg_audit_event_no_update / trg_audit_event_no_delete triggers of db/sqlite/V001__schema.sql.
CREATE OR REPLACE TRIGGER trg_audit_event_append_only
    BEFORE UPDATE OR DELETE ON audit_event
BEGIN
    RAISE_APPLICATION_ERROR(-20001, 'AUDIT_EVENT is append-only');
END;
/
