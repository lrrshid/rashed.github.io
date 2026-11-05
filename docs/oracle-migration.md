# Moving from the SQLite demo to Oracle

The app runs on SQLite (`APP_PROFILE=demo`) with the brochure-shaped demo data, and on Oracle
(`APP_PROFILE=oracle`) for real use. The two schemas are kept identical by **twin scripts**: every
`db/sqlite/V…` script has an Oracle twin in `db/oracle/` whose header names it.

| SQLite | Oracle | Content |
|---|---|---|
| `V001__schema.sql` | `V001__schema.sql` | all tables (security, lists, capability records, projects, history) |
| (indexes inside V001) | `V002__indexes.sql` | indexes, case-insensitive unique username |
| (triggers inside V001) | `V003__audit_append_only.sql` | `AUDIT_EVENT` refuses UPDATE and DELETE |
| `V002__testing_maintenance_ai.sql` | `V004__testing_maintenance_ai.sql` | tests, maintenance orders, AI technologies and levels, development opportunities |
| `V003__documents_alerts.sql` | `V005__documents_alerts.sql` | versioned documents (append-only versions), alert rules and acknowledgements |

Rule: a schema change is a **new numbered script in both folders** (never edit an applied script), plus its runtime
grant in section 3 below.

## 1. Two database accounts

* **Owner** (e.g. `CPC_OWNER`): owns the tables; runs the scripts. Needs `CREATE SESSION, CREATE TABLE,
  CREATE SEQUENCE, CREATE TRIGGER` and quota on its tablespace.
* **Runtime** (e.g. `CPC_APP`): what the app signs in as (`ORACLE_USER`). Only `CREATE SESSION` plus the grants
  below. Set `ORACLE_SCHEMA=CPC_OWNER` so the app's unqualified names resolve to the owner's tables.

## 2. Apply the scripts (as the owner)

```
sqlplus CPC_OWNER@//dbhost:1521/CPCPDB
SQL> WHENEVER SQLERROR EXIT FAILURE
SQL> @db/oracle/V001__schema.sql
SQL> @db/oracle/V002__indexes.sql
SQL> @db/oracle/V003__audit_append_only.sql
SQL> @db/oracle/V004__testing_maintenance_ai.sql
SQL> @db/oracle/V005__documents_alerts.sql
```

Oracle has no `SCHEMA_VERSION` table: record which `V…` scripts were applied in the DBA's change log. At start-up
the app checks that every table and column it maps exists (`flask --app wsgi check-schema` does the same) and stops
with a clear message if one is missing.

## 3. Runtime grants (as the owner)

Business records are never deleted (they are archived), so the runtime account gets no DELETE on them.

```sql
-- every business and list table: read, add, change
GRANT SELECT, INSERT, UPDATE ON app_role TO CPC_APP;
GRANT SELECT, INSERT, UPDATE ON app_user TO CPC_APP;
GRANT SELECT, INSERT, UPDATE, DELETE ON role_permission TO CPC_APP;   -- a role's permission list is edited
GRANT SELECT, INSERT, UPDATE, DELETE ON user_department TO CPC_APP;   -- a user's departments are edited
GRANT SELECT, INSERT, UPDATE, DELETE ON app_session TO CPC_APP;       -- sign-out and expiry delete sessions
GRANT SELECT, INSERT ON audit_event TO CPC_APP;                       -- append-only
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
-- every sequence
BEGIN
  FOR s IN (SELECT sequence_name FROM user_sequences) LOOP
    EXECUTE IMMEDIATE 'GRANT SELECT ON ' || s.sequence_name || ' TO CPC_APP';
  END LOOP;
END;
/
```

Grant `SELECT`, not `READ`: `READ` does not allow the `SELECT … FOR UPDATE` row locks the app takes before changes.

## 4. Reference data and the first administrator

The demo data is never written to Oracle. On a new Oracle schema:

```
cd backend
flask --app wsgi create-user --username U12345 --role SYS_ADMIN      (roles are created first automatically)
flask --app wsgi seed-reference --actor U12345                       (departments, categories, statuses, workflows, spec fields)
```

With `AUTH_MODE=ldap` (see `docs/LDAP_SETUP.txt`) no password is asked: the person signs in with their Windows
password. The emergency account is set with `flask --app wsgi set-break-glass-password` (`BREAK_GLASS_USERNAME` in
`ldap.env`).

## 5. Oracle specifics handled in code

* Session time zone `+00:00`; instants are stored as UTC and read with `SYS_EXTRACT_UTC`.
* `''` is NULL on Oracle: the API turns blank optional text into null before saving.
* CLOB columns are never compared in SQL (compared in Python where needed).
* Row locks use `FOR UPDATE OF <table>.id` (a bare table renders an empty column list on Oracle).
* The `status_def` domain column is `status_domain` (DOMAIN is a keyword from Oracle 23ai).
* Thin mode by default; `ORACLE_THICK_MODE=true` + `ORACLE_CLIENT_LIB_DIR` for Native Network Encryption or
  databases older than 12.1.

## 6. Document files

Uploaded files are stored on the application server under `data/files/<first two hex>/<sha256>` (one copy per content). Include that folder in the server backup together with the database.
