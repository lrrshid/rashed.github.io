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
| `V004__reports.sql` | `V006__reports.sql` | custom report templates, report schedules, report run log |
| `V005__org_units.sql` | `V007__org_units.sql` | directorates and sections that conduct tests (`org_unit`), `test_event.unit_id` |
| `V006__golden_samples_attachments.sql` | `V008__golden_samples_attachments.sql` | golden-sample trials, the reason a capability entered maintenance, new kinds of attached scans (SQLite rebuilds `document` to widen its checks) |
| `V007__settings_connections.sql` | `V009__settings_connections.sql` | Settings > connections: the directory and database connections, their revisions and tests, trusted certificates, approved destinations, the sign-in method (`docs/SETTINGS.md`) |
| `V008__role_levels_and_change.sql` | `V010__role_levels_and_change.sql` | the level of each role in the organisation's structure (`app_role.tier`) and the permission `records.change` (changing and archiving, apart from adding); every role holding an `edit.*` permission is given it, so existing roles keep working (no new table, no new grant) |
| `V009__action_log.sql` | `V011__action_log.sql` | user tracking: `action_log` (every action of every person, carried out or refused; append-only, with its trigger) and the permission `tracking.view`, given to every role holding `admin`; runtime grant `SELECT, INSERT ON action_log` |

Rule: a schema change is a **new numbered script in both folders** (never edit an applied script), plus its runtime
grant line in `db/oracle/runtime-grants.sql` (section 3).

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
SQL> @db/oracle/V006__reports.sql
SQL> @db/oracle/V007__org_units.sql
SQL> @db/oracle/V008__golden_samples_attachments.sql
SQL> @db/oracle/V009__settings_connections.sql
SQL> @db/oracle/V010__role_levels_and_change.sql
SQL> @db/oracle/V011__action_log.sql
```

Oracle has no `SCHEMA_VERSION` table: record which `V…` scripts were applied in the DBA's change log. At start-up
the app checks that every table and column it maps exists (`flask --app wsgi check-schema` does the same) and stops
with a clear message if one is missing.

## 3. Runtime grants (as the owner)

Business records are never deleted (they are archived), so the runtime account gets no DELETE on them. The
grants are in **`db/oracle/runtime-grants.sql`** (one list: the DBA runs it, Settings > Database checks a new
database against it, and the Oracle tests apply it). It names the runtime account `CPC_APP`; change that first
if yours is called differently. Run it as the owner after the scripts:

```
SQL> @db/oracle/runtime-grants.sql
```

A new table gets its line in that file in the same change as its `V0xx` script (V009: the Settings connection
tables, `setting_*`, `egress_rule`, `connection_setting`, `process_heartbeat`).

Grant `SELECT`, not `READ`: `READ` does not allow the `SELECT … FOR UPDATE` row locks the app takes before changes.

## 4. A clean start: the first administrator and the standard lists

The Oracle database **starts clean** (owner, 24 Nov 2026): the demo data (the fictional records and the `mock.*`
accounts that made them) is never written to it, never copied to it, and the app **refuses to start** on an Oracle
database that holds it. Do not copy the demo database. On the new, empty schema (scripts and grants only), with the
app's server file pointing at it:

```
cd backend
flask --app wsgi setup-database --admin U12345 --display-name "Full Name"
```

It creates the roles, the first system administrator (a hidden password prompt) and the standard lists (groups,
capability types, statuses, workflows, specification fields, directorates and sections), and refuses a database that
already has accounts. (The two older steps still work: `create-user --role SYS_ADMIN`, then `seed-reference --actor`.)
The website's **Settings > Database** tests a new database before the move, with read-only checks, and refuses one
that holds the demo data (`docs/SETTINGS.md`).

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

Uploaded files are stored on the application server under `data/files/<first two hex>/<sha256>` (one copy per content). Include that folder in the server backup together with the database. On the Docker VM it is
`/opt/cpc/data/files` (`bash ./scripts/app.sh backup`; see `deployment/README.md`).

## 7. Scheduled reports

Run `flask --app wsgi run-schedules` once a day (Windows Task Scheduler; on the Docker VM cron with `bash ./scripts/app.sh flask run-schedules`, see
`deployment/README.md` section 4) and `flask --app wsgi take-snapshot` once a day for the KPI trends. Generated files go to `REPORTS_OUTPUT_DIR/<output folder>/<date>/` (a local folder or a shared folder on the local network; the system is air-gapped and sends no e-mail) and can be downloaded from Reports > Report history.

## 8. Testing against a local Oracle

`backend/tests/oracle` runs the application on a real Oracle database exactly as it will run in production: it
creates two throwaway accounts (`CPC_T_OWNER`, `CPC_T_APP`) with random passwords, applies `db/oracle/V*.sql` with
sqlplus, grants the runtime account only what section 3 lists, exercises every kind of record, the computed views,
reports and exports, checks that the audit trail is append-only and that business records cannot be deleted, then
drops both accounts.

```
# oracle-local.env in the project folder (git-ignored): ORACLE_DSN, ORACLE_SYSTEM_USER, ORACLE_SYSTEM_PASSWORD
cd backend
..\.venv\Scripts\python.exe -m pytest -m oracle tests/oracle -o addopts=
```

sqlplus must be on PATH. Verified on Oracle Database 26ai Free (thin mode), 5 Nov 2026.
