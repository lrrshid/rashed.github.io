# Capability Portfolio Command

One trusted source for what we have, what we need, what is operational, what is being acquired, developed and
tested, what is delayed, and what requires leadership attention. Bilingual (Arabic / English, RTL / LTR).

Specification: `Capability_Portfolio_Command_Brochure_AR 2.pdf`. Stack and conventions follow ship-project
(Flask + SQLAlchemy, plain-JS frontend, SQLite demo → Oracle, company-directory sign-in).

## Start

```
copy .env.example .env
powershell -ExecutionPolicy Bypass -File scripts\run_dev.ps1
```

Open http://127.0.0.1:8770 and sign in as `mock.admin` (password `Mock-Pass-123`). The first start creates
`data/cpc-demo.db` and seeds the fictional demo world (4 departments, 4 categories, 12 models, 66 assets,
15 requirements, 14 projects, 140 milestones, risks, issues, 13 months of KPI history).

## Air-gapped installation (the target network has no internet)

Everything runs on the local network: the application server, the database (SQLite demo or Oracle), the company
directory (LDAP) and the browsers. There is no e-mail, no CDN and no online service; fonts and icons are in the project.

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
| 0 Foundation | config, SQLite/Oracle DB layer, migrations, 9 roles + permission matrix + department scope, admin role preview, audit, LDAP sign-in, sessions/CSRF/throttle, bilingual shell, login | **done** |
| 1 Capabilities | requirements, models, assets (CRUD, audit, status history), registry with 11 filters + saved views + table/cards, per-category card views, asset / model / requirement profiles, structured technical specs, completion, gap analysis | **done** |
| 2 Executive dashboard | KPI tiles with month/quarter/year trends, attention list, dept × category matrix, status distribution, completion rings, current vs forecast, gap heatmap, sites, portfolio overview, completion timeline; every figure drills to its records (+ CSV) | **done** |
| 3 Projects | portfolio KPIs + charts, project profile with 6 RAG indicators and reasons, workflow path, milestones, project and portfolio Gantt, strategic timeline (month…5 years), risk register with P×I matrix, issues | **done** |
| 4 Operations | testing & evaluation (KPIs, results by model, history; feeds the project testing indicator), maintenance & technical readiness, AI capability levels L0–L5 with met/missing trace and technology matrix, development potential, decision support (11 factual panels with basis) | **done** |
| 5 Administration | versioned documents (type checked from the bytes, append-only versions, department scope), alert centre (16 types, role rules, per-user acknowledgement), global search, settings (lists, statuses, workflows with reordering, spec fields, AI levels, business rules, roles and permission matrix, users, alert rules, audit history) | **done** |
| 6 Reports | 117 predefined reports in 11 categories (EN / AR / bilingual, inheriting permissions and scope, header with generation details, filters and classification), executive summary, monthly leadership report (changes since last month), trend reports, custom report builder with saved templates, scheduled reports (`run-schedules`), run history; exports: Excel (RTL sheets in Arabic), CSV, PowerPoint, PDF / print-ready PDF via the print view | **done** |
| 7 Hardening | air-gapped: no e-mail anywhere (scheduled reports go to a folder and the report history), offline installation from `wheelhouse\\` (`scripts/build_wheelhouse.ps1`, verified with `pip --no-index`); done: frontend checks without a browser (`scripts/check_frontend.py`: every module compiles, imports resolve, all 521 label keys exist in EN and AR), Oracle script parity tests (every mapped table, column and sequence exists in `db/oracle`). Verified on a real Oracle Database 26ai Free (5 Nov 2026): all scripts apply, the app runs as the restricted runtime account with only the documented grants, and the Oracle suite (`tests/oracle`) passes. **Still open:** a visual pass of the phase 4-6 pages in the browser (EN and AR, desktop and phone), Playwright e2e tests, real PDF rendering beyond the browser print view | partly done |

Pages of later phases already appear in the navigation with a placeholder.

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
`scripts\run_tests.ps1` runs the unit + integration suite (335 tests) and the frontend checks. `..\.venv\Scripts\python.exe -m pytest` from `backend/` (unit + integration; the e2e and oracle markers are opt-in).
