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

## Handover: read this first

### Build plan and state (4 Nov 2026)

| Phase | Scope | State |
|---|---|---|
| 0 Foundation | config, SQLite/Oracle DB layer, migrations, 9 roles + permission matrix + department scope, admin role preview, audit, LDAP sign-in, sessions/CSRF/throttle, bilingual shell, login | **done** |
| 1 Capabilities | requirements, models, assets (CRUD, audit, status history), registry with 11 filters + saved views + table/cards, per-category card views, asset / model / requirement profiles, structured technical specs, completion, gap analysis | **done** |
| 2 Executive dashboard | KPI tiles with month/quarter/year trends, attention list, dept × category matrix, status distribution, completion rings, current vs forecast, gap heatmap, sites, portfolio overview, completion timeline; every figure drills to its records (+ CSV) | **done** |
| 3 Projects | portfolio, project profile + 6 RAG indicators (health logic done in `project_health.py`), workflows, milestones, Gantt, strategic timeline, risks, issues | next — data model, seed and health rules exist; pages and APIs to build |
| 4 | testing & evaluation, maintenance & technical readiness, AI capability level, development potential, decision support | to do |
| 5 | documents (versioned), alert centre (16 types), global search (basic version done), settings UI (lists, statuses, workflows, spec fields, business rules, roles matrix, users) | to do |
| 6 | reports: ~130 defined reports, leadership monthly report, custom builder, schedules, PDF/Excel/CSV/PowerPoint | to do (CSV of assets done) |
| 7 | hardening: Oracle run, phone layouts, Playwright e2e | to do |

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
- `take-snapshot` (daily KPI values) · `check-ldap [--username U12345]` · `set-break-glass-password` · `purge-sessions`

### Tests
`..\.venv\Scripts\python.exe -m pytest` from `backend/` (unit + integration; the e2e and oracle markers are opt-in).
