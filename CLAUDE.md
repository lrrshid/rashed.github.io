# Capability Portfolio Command

Capability management information system + project portfolio manager (spec: `Capability_Portfolio_Command_Brochure_AR 2.pdf`).
Flask + SQLAlchemy backend (`backend/app`), plain-JS ES-module frontend (`frontend/`, no bundler), SQLite demo DB in
`data/`, twin SQLite/Oracle DDL in `db/`. Flask serves the API (`/api/v1`) and the frontend. Database conventions and
the LDAP sign-in are inherited from github.com/MAZ-1234/ship-project.

**Read the "Handover" section of README.md before changing anything** and update it when you finish a piece of work.

## Commands (from repo root)
- Run: `powershell -ExecutionPolicy Bypass -File scripts\run_dev.ps1` -> http://127.0.0.1:8770 (ports 8080/8090/8765 are used by other apps on this PC)
- Tests: `powershell -ExecutionPolicy Bypass -File scripts\run_tests.ps1`, or from `backend/`: `..\.venv\Scripts\python.exe -m pytest`
- Reset demo data: stop the server, delete `data/cpc-demo.db*`, start again (re-seeds).
- Demo sign-in: `mock.admin`, `mock.exec`, `mock.head` (Group 2 only), `mock.capability`, `mock.pm`, `mock.maint`, `mock.test`, `mock.analyst`, `mock.viewer`; password `Mock-Pass-123`.

## Rules
- The system runs on an **air-gapped** local network: nothing may need the internet (no e-mail/SMTP, no CDN, no
  online APIs, no runtime downloads). Scheduled reports go to `REPORTS_OUTPUT_DIR` and the report history; Python
  packages install from `wheelhouse\` (`scripts/build_wheelhouse.ps1`); third-party files are vendored.
- Permissions are enforced server-side through the helpers in `backend/app/security/auth.py` (`has_permission`,
  `require_edit`, `require_admin`, `department_scope`, `require_department_access`). Never compare role codes elsewhere.
  Roles and their permissions are data (`APP_ROLE`, `ROLE_PERMISSION`); a role's scope is ALL or DEPARTMENT
  (`USER_DEPARTMENT`); out-of-scope records answer 404. The admin "view as" preview (`X-View-As`) is read-only.
  Never rely on the UI to enforce any of this.
- Every figure is computed from source records (`services/metrics_service.py`, `project_health.py`,
  `snapshot_service.py`), never typed in, and carries a `drill` (asset filters) that lists exactly the records it
  counts. Keep `tests/integration/test_capabilities.py::test_every_dashboard_asset_figure_equals_its_drill_down` green.
- Business rules (available / operational / pipeline statuses, forecast statuses, health thresholds, readiness
  weights) live in `APP_SETTING` via `services/settings_service.py`, defaults in `seed/reference_data.py`.
- Records are created, changed, archived and restored through `services/crud.py` (permission + scope, stamps,
  optimistic `version` -> 409 STALE_VERSION, an `AUDIT_EVENT` row in the same transaction). Archive, never delete.
- Schema changes: a new numbered script in both `db/sqlite/` and `db/oracle/` (never edit an applied one), plus the
  runtime grant in `docs/oracle-migration.md`. Tables are never created by `create_all()`.
- The mock accounts and `MOCK_PASSWORD` are a public demo placeholder: never on the Oracle profile.
- `.env`, `ldap.env` and `oracle-local.env` are never committed and their values never printed.
- Directory sign-in (`AUTH_MODE=ldap`, settings in `ldap.env`, guide `docs/LDAP_SETUP.txt`): LDAP code only in
  `backend/app/security/directory.py` (tests inject ldap3 MOCK_SYNC via `app.config["DIRECTORY_CONNECTION_FACTORY"]`).
  Only active APP_USERs get in; roles/departments come from the app; only the display name follows the directory.
  Never bypass the directory except for the single break-glass SYS_ADMIN (`BREAK_GLASS_USERNAME`). ldaps/starttls only.
- Frontend: vanilla JS modules, pages in `frontend/js/pages`, components in `frontend/js/components`. No inline
  scripts or `style=""` attributes (CSP); set styles through `h(..., { style })`, which uses CSSOM.
- Arabic: every UI string in `frontend/js/labels.js` has its twin under the same key in `frontend/js/i18n/ar/index.js`;
  records carry `nameEn`/`nameAr` (pick with `name()`); CSS uses logical properties, RTL-only rules in `css/rtl.css`;
  Western digits, dd/mm/yyyy dates.
- Match existing code style; keep tests in sync with changes.
