# Capability Portfolio Command

One trusted source for what we have, what we need, what is operational, what is being acquired, developed and
tested, what is delayed, and what requires leadership attention. Bilingual (Arabic / English, RTL / LTR).

Specification: `Capability_Portfolio_Command_Brochure_AR 2.pdf`. Stack and conventions follow ship-project
(Flask + SQLAlchemy, plain-JS frontend, SQLite demo → Oracle, company-directory sign-in).

Shown to users as **National Guard Capability System / نظام قدرات الحرس الوطني**, subtitle «Capability management / إدارة القدرات» (`app.name` in `frontend/js/labels.js`
and `frontend/js/i18n/ar/index.js`; Excel/PowerPoint export metadata in `backend/app/core/xlsx.py`, `pptx.py`) with
the National Guard shield as logo and favicon (`frontend/assets/icons/ng-logo.png`, cut from the official logo).
Arabic wording: a department is «المجموعة» (plural «المجاميع», the all-departments filter «مجاميع الحرس الوطني»), a
failed test «غير ناجح», executive reports «التقارير الرئيسية», a milestone owner «مدير المشروع». Some Arabic report
titles are worded by hand (`_AR_TITLE_OVERRIDES` in `report_service.py`). English labels are unchanged.

## Start

```
copy .env.example .env
powershell -ExecutionPolicy Bypass -File scripts\run_dev.ps1
```

Open http://127.0.0.1:8770 and sign in as `mock.admin` (password `Mock-Pass-123`; one demo account per role:
`mock.commander`, `mock.admin`, `mock.capdev`, `mock.security`, `mock.unmanned`, `mock.pm`, `mock.user`). The first start creates
`data/cpc-demo.db` and seeds the fictional demo world (4 departments, 4 categories, 12 models, 66 assets,
15 requirements, 14 projects, 140 milestones, risks, issues, 13 months of KPI history).

## Air-gapped installation (the target network has no internet)

Everything runs on the local network: the application server, the database (SQLite demo or Oracle), the company
directory (LDAP) and the browsers. There is no e-mail, no CDN and no online service; fonts and icons are in the project.

**The company's Linux VM (Docker): read `internet-to-local.md`.** On the internet-connected PC,
`predeployment\build.ps1` builds one file `dist\cpc-<version>.tar.gz` (the app image, nginx, the deployment files,
the Oracle scripts); on the VM it is unpacked and started with `scripts/install.sh` (`deployment/README.md`).

**A Windows server instead** (the steps below): the same offline packages from `wheelhouse\`; in production run
`python serve.py` from `backend\` behind the company HTTPS proxy with `TRUSTED_PROXY_COUNT` set.

1. On a machine **with** internet access, once: `powershell -ExecutionPolicy Bypass -File scripts\build_wheelhouse.ps1`
   (all pinned Python packages for Windows 64-bit / Python 3.12 into `wheelhouse\`; add `-Production` for runtime
   packages only).
2. Copy to the air-gapped server: the project folder **with** `wheelhouse\`, and the Python 3.12 Windows installer.
3. On the server: install Python 3.12, `copy .env.example .env`, then `scripts\run_dev.ps1`. It installs only from
   `wheelhouse\` (`pip --no-index`), never from the internet.
4. Scheduled reports are written to `REPORTS_OUTPUT_DIR` (default `data\reports`; can be a shared folder on the local
   network such as `\\fileserver\CPC-Reports`), one sub-folder per schedule and date, and can be downloaded from
   Reports > Report history. Schedule `flask --app wsgi run-schedules` and `flask --app wsgi take-snapshot` daily
   with the Windows Task Scheduler.

## Handover: read this first

### Build plan and state (4 Nov 2026)

| Phase | Scope | State |
|---|---|---|
| 0 Foundation | config, SQLite/Oracle DB layer, migrations, roles + permission matrix + department scope, admin role preview, audit, LDAP sign-in, sessions/CSRF/throttle, bilingual shell, login | **done** |
| 1 Capabilities | requirements, models, assets (CRUD, audit, status history), registry with 11 filters + saved views + table/cards, per-category card views, asset / model / requirement profiles, structured technical specs, completion, gap analysis | **done** |
| 2 Executive dashboard | KPI tiles with month/quarter/year trends, attention list, dept × category matrix, status distribution, completion rings, current vs forecast, gap heatmap, sites, portfolio overview, completion timeline; every figure drills to its records (+ CSV) | **done** |
| 3 Projects | portfolio KPIs + charts, project profile with 6 RAG indicators and reasons, workflow path, milestones, project and portfolio Gantt, strategic timeline (month…5 years), risk register with P×I matrix, issues | **done** |
| 4 Operations | testing & evaluation (KPIs, results by model, history; feeds the project testing indicator), maintenance & technical readiness, AI capability levels L0–L5 with met/missing trace and technology matrix, development potential, decision support (11 factual panels with basis) | **done** |
| 5 Administration | versioned documents (type checked from the bytes, append-only versions, department scope), alert centre (16 types, role rules, per-user acknowledgement), global search, settings (lists, statuses, workflows with reordering, spec fields, AI levels, business rules, roles and permission matrix, users, alert rules, audit history) | **done** |
| 6 Reports | 117 predefined reports in 11 categories (EN / AR / bilingual, inheriting permissions and scope, header with generation details, filters and classification), executive summary, monthly leadership report (changes since last month), trend reports, custom report builder with saved templates, scheduled reports (`run-schedules`), run history; exports: Excel (RTL sheets in Arabic), CSV, PowerPoint, PDF / print-ready PDF via the print view | **done** |
| 7 Hardening | air-gapped: no e-mail anywhere (scheduled reports go to a folder and the report history), offline installation from `wheelhouse\\` (`scripts/build_wheelhouse.ps1`, verified with `pip --no-index`); done: frontend checks without a browser (`scripts/check_frontend.py`: every module compiles, imports resolve, all 521 label keys exist in EN and AR), Oracle script parity tests (every mapped table, column and sequence exists in `db/oracle`). Verified on a real Oracle Database 26ai Free (5 Nov 2026): all scripts apply, the app runs as the restricted runtime account with only the documented grants, and the Oracle suite (`tests/oracle`) passes. Visual pass of the phase 4-6 pages in Edge at 1440px, EN and AR (5 Nov 2026): no console errors; fixed narrow-column wrapping, the AI matrix headers, permission labels, the wrapping tab bar, and raw codes / ISO dates in Arabic reports, decision panels and alerts (`report_service.CODE_LABELS`, dd/mm/yyyy in panel and alert text). The system is **desktop web only**: no phone or tablet work. **Still open:** Playwright e2e tests, real PDF rendering beyond the browser print view | partly done |

Pages of later phases already appear in the navigation with a placeholder.

**Look and colours (11 Nov 2026).** The sign-in page and the home page banner show an animated capability scene
(`frontend/js/components/scene.js`, `css/scene.css`: drones, radar, sea and ground vehicles, drawn as SVG, no video
file, no external files; still when the viewer prefers reduced motion). Interface colours are a setting (`ui.theme`:
side bar, buttons, accent, background) edited in Settings > Appearance (palettes + colour pickers, live preview);
`GET /appearance` is public so the sign-in page uses them, and `js/lib/theme.js` derives the CSS variables.
The scene follows the mouse (`followPointer`: depth layers, a gold light, the sign-in card tilts). The top bar has a
light / dark mode button (also on the sign-in page; each browser keeps its choice, `cpc.mode`, applied before the first paint by
`js/lang-boot.js`; dark surfaces are derived from the side-bar colour, printing is always light) and, for
a colours button (top bar and sign-in page) with ready-made palettes for this device (`cpc.palette`, over the colours
saved for everyone; saving in Settings > Appearance clears it on that device), which also leads administrators to
Settings > Appearance.

**User tracking «تتبع المستخدمين» (25 Nov 2026).** Replaces the user board (owner: the commander sees everything people
do). Every API request that is an action writes one `ACTION_LOG` row (`services/tracking_service.py`, called by the
`api/v1` after-request hook in its own short transaction): sign-ins (failed ones too) and sign-outs, every change asked
for (POST/PUT/PATCH/DELETE), opening a record or a report, downloads and exports; lists, dashboards and look-ups are
not actions. A row keeps who (name and role then), the action, the record (type, code, names), the outcome (carried
out or not) with the error code, message and fields at fault, the file name of an upload or download, the time, the
IP address and the request id; a change carried out points at its audit row (the fields that changed). Never kept:
passwords or other request values (only the code of a record being added); a failed sign-in with a name that is no
account keeps its first three letters. Append-only (triggers). Screen `/user-tracking` (menu «تتبع المستخدمين»;
`/user-board` leads there): filters (days, person, kind, result, search), totals, the actions (details: what
changed) and the people (sign-ins, failed sign-ins, actions, refused ones, signed in now). Permission `tracking.view`
(the five heads of the structure; never in a role preview); API `GET /tracking/actions[/<id>]`, `GET /tracking/users`.
Scripts `db/sqlite/V009`, `db/oracle/V011` (+ the `action_log` grant). The old `/user-activity` endpoints are gone.

**The organisation's structure as the roles (25 Nov 2026).** The standard roles (`reference_data.ROLES`) are now the
owner's structure, top down: القائد `COMMANDER` and مدير النظام `SYS_ADMIN` (level 1), رئيس شعبة تطوير القدرات
`HEAD_CAP_DEV` (2), رئيس شعبة الأنظمة الأمنية `HEAD_SECURITY` and رئيس شعبة الأنظمة المسيّرة `HEAD_UNMANNED` (3),
مدير المشروع `PROJECT_MGR` (4), المستخدم `USER` (5). The first five have every permission (owner: "all permissions,
like the commander", so Settings, users and the user board too); the project manager and the user add and view
only. They replace the nine earlier roles (owner's choice); the demo has one account per role. The new permission
`records.change` separates changing, archiving and restoring from adding: `edit.*` alone adds (`auth.require_change`
in `crud.update` / `crud.set_archived`, a document's second file, a project health note, a model's AI functions;
403 `ADD_ONLY`; frontend `canChange` hides the edit, archive and replace buttons). Settings > Roles shows the structure
(`APP_ROLE.tier`: one row per level, what each role may do in words, active people; the pencil edits names and
level) above the permission matrix. Default alert rules name the new roles. Scripts `db/sqlite/V008`,
`db/oracle/V010` (no new table): every existing role holding an `edit.*` permission is given `records.change`, so
an existing database keeps working; its old roles stay until an administrator moves people (roles are never
deleted). The tests keep the earlier narrow shapes as test-only roles (`tests/conftest.py` TEST_ROLES).

**Users from Excel (24 Nov 2026).** Settings > Users has "Download the Excel template" and "Import from Excel" (`frontend/js/pages/user-import.js`, `backend/app/services/user_import.py`, `GET /users/import-template?lang=`, `POST /users/import/check`, `POST /users/import`). The template (EN/AR) has a role drop-down and an instructions sheet listing the roles and groups. The check reads the file (Excel or CSV) and checks every row with the rules of `user_service.create_user` (codes worded on the page); the import adds every row in one transaction, only when no row has a problem, each audited "Added from an Excel file (row N)". Passwords are hashed and never returned; with directory sign-in they are ignored and the username is the Windows name. System administrators only.

**Settings > connections: the directory and the database from the website (24 Nov 2026).** Ported from the
Asset Availability reference project (owner: "implement the same"; system administrators only). Four Settings tabs:
Sign-in and directory, Database, Network and certificates, Connection history (`frontend/js/pages/connections.js`,
API `/api/v1/connections/*`, services `backend/app/services/connections/`, guide `docs/SETTINGS.md`). Each
connection is a profile with numbered revisions: save draft, test (staged, read-only), apply; passwords are encrypted
with AES-256-GCM under `SETTINGS_KEY` (demo: `data/settings.key`), never returned or audited; sensitive steps need the
password typed again (`POST /connections/reauth`). The directory and the sign-in method apply within seconds through
`config_service.effective()` (`context.settings()` and the sign-in code read it). The database is never switched from
the website: a candidate is tested (connect, schema, the grants of `db/oracle/runtime-grants.sql`, data) and staged;
IT changes the server file and restarts. **Clean start** (owner): the data stage fails on any `mock.*` account (the
demo world is made by them), the Oracle profile refuses to start on such a database, `mock.*` names are reserved for
the local demo, and `flask setup-database --admin <name>` makes the first administrator and the standard lists on the
empty database. Recovery: `flask settings-recover`, key rotation: `flask settings-rotate-key`. Schema: `db/sqlite/V007`,
`db/oracle/V009`; the runtime grants moved from `docs/oracle-migration.md` into `db/oracle/runtime-grants.sql`. Not
yet done from the reference: Keycloak SSO, AI servers, interface texts and logo, a Developer role.

**Scans, golden samples, culture and the user board (24 Nov 2026).** Attached scans reuse the versioned documents:
`document_service.SLOTS` gives some records fixed places for a scan (a test: capability deed «سند القدرة» and the live
demonstration report for inspection; a maintenance order: the investigation board «هيئة التحقيق»; a golden-sample
trial: the trial, the higher-level directive letter and the official trial form). `POST /attachments` puts a scan in
its slot (the first scan makes the document, later ones are new versions); forms send chosen files after saving the
record (`components/attachments.js`, form field `type: 'file'`). New pages: Capabilities > «موقف تجارب العينات الذهبية»
(`/golden-samples`, table `golden_sample_trial`, TEST statuses, edited by the testing team); Maintenance > «صيانة القدرة»
(`/maintenance/capability`: `maintenance_order.entry_reason_en/ar` and the investigation scan); «الثقافة» in the side
menu (`/culture/references|guide|acquisition`: documents of the entity `LIBRARY`, id 1, kinds REFERENCE, USER_GUIDE,
ACQUISITION_PLAN, only there); «لوحة عرض المستخدم» (`/user-board`; since 25 Nov replaced by user tracking, see above): each user's activity from the audit trail, which now also records SIGN_IN and SIGN_OUT.
Scripts `db/sqlite/V006` (rebuilds DOCUMENT to widen its CHECK lists, `-- migrate: foreign-keys-off`) and
`db/oracle/V008` (+ the `golden_sample_trial` grant). The sign-in page no longer lists the demo accounts.

**The VM kit with one installer (25 Nov 2026).** Owner: "a kit with an executable bash file to move the web to the
air-gapped VM; it has Docker and nginx". `predeployment\build.ps1` makes `dist\cpc-<version>.tar.gz` (pack.py keeps
Linux permissions: `./install.sh` runs straight after `tar -xzf`). `deployment/install.sh` (no Docker Compose needed)
asks the name users type, the database (built-in SQLite file in `/opt/cpc/data`, `APP_PROFILE=demo` +
`APP_ENV=production` = empty, no mock accounts; or Oracle), the first administrator and their password; loads the image
offline, installs into `/opt/cpc`, writes `app.env` with a new `SETTINGS_KEY`, uses IT's certificate or makes a
self-signed one, runs `cpc-app` on `127.0.0.1:8770` (read-only, no capabilities), adds `cpc.conf` to the VM's nginx
(`http.d` or `conf.d`; `nginx -t` first, the previous site kept in `backups/`; SELinux boolean), or runs the bundled
nginx container when the VM has none, checks the site through nginx, runs `setup-database --password-stdin` (new
option), installs `/etc/cron.d/cpc`. Re-running it updates (backup first; settings, data, certificate kept).
`scripts/app.sh`: status, logs, restart, check, flask, backup (a consistent SQLite copy + scans + settings, 14 days).
Guides `deployment/README.md` (IT) and `README-AR.md`; `internet-to-local.md` rewritten. Verified 25 Nov 2026: the kit
(86 MB) installed with `--yes` on two stand-in VMs (docker:27.5.1-dind containers cut off from the network, so nothing
could be downloaded), one with nginx 1.26 (Alpine, `http.d`) and one without (bundled nginx); on both: health, page and
security headers through nginx, http→https, admin sign-in, only that account, no demo records, seven roles, adding a
person, user tracking, a 3 MB upload through nginx, `app.sh check` and `backup`; an update run kept the data. Found and
fixed on the way: the image did not start without `SETTINGS_KEY` on a read-only filesystem (the build's test start now
passes one; `install.sh` always writes one). Not yet tried: a real Linux VM (RHEL/Ubuntu, systemd, SELinux).

**Offline deployment bundle (18 Nov 2026).** `internet-to-local.md` is the guide for moving the system to the
company's offline Linux VM: `predeployment/` (Dockerfile, `build.ps1`), `deployment/` (docker-compose with the app
behind nginx HTTPS, `app.env.example`, `scripts/install.sh` and `scripts/app.sh`, the VM install guide),
`docs/IT_REQUEST.md` (what to ask IT and the DBA). The production server is `backend/serve.py`: waitress, one
process (the sign-in throttle is in memory), and behind a proxy it keeps the `X-Forwarded-*` headers that waitress
otherwise strips (all users would have shared the proxy's address in the per-address sign-in limit).
`tests/unit/test_deployment.py` keeps the pieces consistent. Verified 18 Nov 2026 with Docker 29.9.3: the bundle
builds (86 MB) and runs under Compose behind nginx (see `internet-to-local.md` section 9 for what was checked);
`install.sh` was exercised with a stand-in docker in Git Bash. Still to try: the Oracle profile in the container and a
real Linux VM.

**Conducting units (11 Nov 2026).** Tests record the section that conducts them (`test_event.unit_id`). Units are a
two-level list `org_unit` (a directorate, then its sections; Settings > «Directorates and sections»), seeded as
«مديرية تطوير القدرات» with «شعبة الأنظمة الأمنية» and «شعبة تطوير القدرات» (`reference_data.ORG_UNITS`). The testing
page filters by a directorate (all its sections) or one section (`GET /tests?unit=`), and the reports have «Tests by
conducting section». Units do not limit access (department scope is unchanged). Scripts `db/sqlite/V005`,
`db/oracle/V007`; on an existing Oracle schema run V007, the `org_unit` grant, then `seed-reference`.

### Where things are
- `backend/app/services/metrics_service.py` — completion, gaps, heatmap, matrix (the formulas; see its docstring).
- `backend/app/services/project_health.py` — the six project indicators and their reasons.
- `backend/app/services/dashboard_service.py`, `snapshot_service.py` — dashboard and KPI trends.
- `backend/app/services/crud.py` — the one audited create/update/archive path.
- `backend/app/security/auth.py` — every permission rule; `directory.py` — LDAP.
- `backend/app/seed/` — reference lists (`reference_data.py`) and demo world (`fixture_data.py`, `demo_seeder.py`).
- `frontend/js/pages/` — one module per page; `components/drilldown.js` — figure → records.
- `db/sqlite`, `db/oracle` — twin schema scripts; `docs/oracle-migration.md` — DBA guide and grants.
- `docs/LDAP_SETUP.txt`, `docs/LDAP_IT_MANUAL.md`, `ldap.env.example` — directory sign-in.

### Commands (from `backend/`)
- `flask --app wsgi check-schema` · `create-user --username U12345 --role SYS_ADMIN` · `seed-reference --actor U12345`
- `take-snapshot` (daily KPI values) · `run-schedules` (daily scheduled reports) · `check-ldap [--username U12345]` · `set-break-glass-password` · `purge-sessions`

### Tests
`scripts\run_tests.ps1` runs the unit + integration suite (420 tests) and the frontend checks. `..\.venv\Scripts\python.exe -m pytest` from `backend/` (unit + integration; the e2e and oracle markers are opt-in).
