# Internet to local: moving Capability Portfolio Command to the company's local VM

**Audience:** an agent (or engineer) asked to deploy or update this project on the company's **offline local
virtual machine**. Read this file first; it lists every piece, where it lives in the repository, what IT and the DBA
must supply, and the exact order of work. The detailed guides it points to stay the source of truth for their topic.

## 1. The situation in one paragraph

The project is developed on an **internet-connected Windows PC** (this repository, Docker Desktop, Python, Git). The
target is a **Linux VM on the company network with no internet**. The VM never downloads anything: on the
internet-connected PC we build a **Docker image** of the app, pull the **nginx** image, and pack both, together with the
deployment files, into **one `.tar.gz` bundle**. That one file is carried to the VM (USB or the company's approved file
transfer), unpacked, configured with the company's values, and started with Docker Compose. The records live in the
company's **Oracle** database; the uploaded document files and scheduled reports live on the VM in `/opt/cpc/data`.

```
 Internet PC (Windows)                         Company network (offline)
 ────────────────────────                      ───────────────────────────────────────────────────────
 repo ─▶ tests ─▶ predeployment/build.ps1      Local VM (Linux, Docker)
               │  docker build (Dockerfile)      /opt/cpc/   (the unpacked bundle)
               │  test start on :18080           ├─ proxy  nginx:1.27.3-alpine  :443 (HTTPS), :80 → 443
               │  docker pull nginx              │     └─▶ app:8080
               │  docker save (2 images)         └─ app    cpc:<version>  (waitress + Flask)
               ▼                                        ├─▶ Oracle  (DBA; schema V001–V007)
   dist/cpc-<version>.tar.gz ──────────────────▶        ├─▶ LDAP / AD (optional, ldap.env)
                 (one file, ~150 MB)                    └─  /app/data = /opt/cpc/data (documents, reports)
```

## 2. What exists in the repository

| Path | Used on | What it is |
|---|---|---|
| `predeployment/Dockerfile` | internet PC | The app image: `python:3.12.10-slim-bookworm`, installs `backend/requirements.txt` (pinned by `constraints.txt`), copies `backend/` (no tests), `frontend/`, `db/`; runs as user `app` (uid 10001); only `/app/data` is writable; `HEALTHCHECK` on `/api/v1/health`; `CMD python serve.py` |
| `predeployment/build.ps1` | internet PC | Builds the bundle: tests → `docker build` → a test start on port 18080 (read-only, health + page + script + security headers) → `docker pull nginx:1.27.3-alpine` → assembles `dist\cpc-<version>\` → `docker save` both images → LF line endings → `SHA256SUMS` → `.tar.gz`. `-Platform linux/arm64` for an ARM VM |
| `predeployment/README.md` | internet PC | The build checklist |
| `.dockerignore` | internet PC | Allow-list: only `backend/` (minus tests and dev files), `frontend/`, `db/`; never secrets or `data/` |
| `backend/serve.py` | image | The production server: waitress, **one process**, `APP_THREADS` threads (default 8), `APP_LISTEN`. Behind a proxy (`TRUSTED_PROXY_COUNT` > 0) it lets the `X-Forwarded-*` headers through to ProxyFix (waitress strips them by default) |
| `deployment/docker-compose.yml` | VM | Two services: `app` (read-only filesystem, `cap_drop: ALL`, `no-new-privileges`, `/tmp` as tmpfs, `./data` → `/app/data`, `./ldap` → `/app/ldap` read-only, `env_file: app.env` + optional `ldap.env`) and `proxy` (nginx, ports `${HTTPS_PORT:-443}` and `${HTTP_PORT:-80}`, waits for the app to be healthy). Needs **Docker Compose 2.24+** |
| `deployment/app.env.example` | VM | The settings template: profile, Oracle, capacity, sign-in, reports folder. Copied to `app.env` on the VM |
| `deployment/nginx/nginx.conf` | VM | The HTTPS reverse proxy (section 6) |
| `deployment/nginx/certs/README.md` | VM | Where IT's certificate and key go (`server.crt`, `server.key`) |
| `deployment/ldap/README.md` | VM | Directory sign-in in the container (CA certificate in `ldap/`, settings in `ldap.env`) |
| `deployment/scripts/install.sh` | VM | First install or update: checks `SHA256SUMS`, `app.env` (no placeholders, `APP_PROFILE=oracle`), the certificate and key pair; `docker load`s the images; writes `.env` (`APP_VERSION`, keeps the previous one for rollback); `docker compose up -d`; waits for healthy |
| `deployment/scripts/app.sh` | VM | Everyday commands: `status`, `start`, `stop`, `restart`, `logs`, `wait`, `check` (schema), `version`, `flask <command>`, `backup` |
| `deployment/README.md` | VM | The install guide that ships inside the bundle (install, daily jobs, smoke test, update, rollback, backup) |
| `db/oracle/V001__schema.sql` … `V007__org_units.sql` | DBA | The Oracle schema scripts, run in order by the DBA (bundled as `oracle-scripts/`) |
| `docs/oracle-migration.md` | DBA | Run order, the runtime grant list (section 3), first administrator, Oracle specifics |
| `docs/IT_REQUEST.md` | IT | Everything to ask IT and the DBA for (VM, network, certificate, Oracle, directory, file transfer) |
| `docs/LDAP_IT_MANUAL.md`, `docs/LDAP_SETUP.txt`, `ldap.env.example` | IT | Directory sign-in |
| `backend/tests/oracle` | internet PC | The Oracle suite: applies the scripts to throwaway accounts on a real Oracle and runs the app as the restricted runtime account (`docs/oracle-migration.md` section 8) |
| `backend/tests/unit/test_deployment.py` | internet PC | Keeps these files consistent: every Oracle script is named in the guides, nginx admits the upload limit, no secret enters the image or the bundle, the server keeps the proxy headers |
| `dist/` | internet PC | Where bundles are written (git-ignored; never committed) |

## 3. Requirements

### 3.1 The internet-connected PC (build machine)

- Windows 10/11 with **Docker Desktop** (Linux containers) running, **Git**, **Python 3.12** with the project's `.venv`
  (made by `scripts\run_dev.ps1`).
- Internet access to: Docker Hub (`python:3.12.10-slim-bookworm`, `nginx:1.27.3-alpine`) and PyPI (the pinned
  packages, fetched inside the image build).
- About 2 GB free for the images and the bundle.
- **CPU architecture must match the VM.** Default `linux/amd64`; for an ARM VM (`aarch64`) run
  `build.ps1 -Platform linux/arm64` (Docker Desktop emulates it; slower).

### 3.2 The local VM

- Linux 64-bit with **Docker Engine** and the **Docker Compose plugin 2.24 or newer** (`docker compose version`).
  Offline: IT installs them from the distribution's packages or Docker's `.deb`/`.rpm`.
- At least 2 CPU cores and 4 GB RAM; **4 cores and 8 GB suggested**. Disk: images, logs (rotated at 10 × 20 MB per
  container), and the uploaded documents (up to 20 MB each) and reports in `data/`.
- **Time synchronised (NTP)**: sign-in sessions depend on it.
- `sha256sum`, `tar`, `bash`, `openssl` available (standard).
- A folder for the app, `/opt/cpc`, owned by root, readable by the operator.

### 3.3 Network (ask IT to open)

| From → To | Port | Why |
|---|---|---|
| Users' network → VM | 443 (and 80, which only redirects) | The website |
| VM → Oracle | usually 1521 (or the DBA's TCPS port) | The database |
| VM → domain controllers | 636 (LDAPS) or 389 (StartTLS) | Directory sign-in, if used |
| DNS | — | A name for the app (e.g. `cpc.company.local`) pointing to the VM |

The app makes no other outbound connection: no e-mail, no internet, no CDN.

## 4. What IT and the DBA must supply (collect before building)

Use `docs/IT_REQUEST.md` as the form. In short:

1. **Oracle (DBA):** the DSN (`host:port/service`), a schema-owner account (e.g. `CPC_OWNER`) and a separate runtime
   account (e.g. `CPC_APP`) with its password; the DBA runs `V001`–`V007` as the owner, then the runtime grants
   (`docs/oracle-migration.md` sections 2–3). Wallet/TCPS details only if they require it.
2. **Certificate (IT):** `server.crt` (the certificate for the app's DNS name **followed by the intermediate chain**, PEM)
   and `server.key` (PEM, no password).
3. **DNS name** for the app; users open `https://<name>`, which must match the certificate.
4. **Capacity:** cores and RAM of the VM → `APP_THREADS`; agree `ORACLE_POOL_MAX` (at least `APP_THREADS`) with the DBA.
5. **Sign-in:** Active Directory over LDAP (`docs/LDAP_IT_MANUAL.md`), or until then the app's own passwords. A
   username for the **emergency (break-glass) administrator** (`BREAK_GLASS_USERNAME`).
6. **The approved way to bring a file into the network** (USB policy or file-transfer system) and its size limit
   (the bundle is about 150 MB).

## 5. Step by step

### A. On the internet-connected PC

1. `git pull`; make sure the work is committed (the version becomes `yyyy.MM.dd-<commit>`; uncommitted work gets
   `-dirty`).
2. Run the tests: `powershell -ExecutionPolicy Bypass -File scripts\run_tests.ps1`. All must pass.
3. Recommended for a first move or a schema change: run the **Oracle suite** against a local Oracle
   (`docs/oracle-migration.md` section 8). `V001`–`V006` were verified on Oracle Database 26ai Free (5 Nov 2026);
   **`V007` (org units) has not yet run on a real Oracle**.
4. Start Docker Desktop, then build: `powershell -ExecutionPolicy Bypass -File predeployment\build.ps1`
   (`-SkipTests` only if the tests just passed). Result: `dist\cpc-<version>.tar.gz`.
5. Note the file's SHA-256 (printed by the script, or `Get-FileHash dist\cpc-<version>.tar.gz`).

### B. Carry the bundle

Copy the single `.tar.gz` through the approved channel. Never copy `.env`, `ldap.env`, `oracle-local.env`, `data\` or
any key: the bundle deliberately contains none of them (`build.ps1` refuses to build if one slips in).

### C. On the VM (first install)

Follow `deployment/README.md` (it is inside the bundle). The core commands:

```bash
mkdir -p /opt/cpc && cd /opt/cpc
tar -xzf /path/to/cpc-<version>.tar.gz --strip-components=1
cp app.env.example app.env && chmod 600 app.env
nano app.env                           # fill every <...>: ORACLE_DSN, ORACLE_PASSWORD ...
cp /path/to/server.crt /path/to/server.key nginx/certs/
sudo bash ./scripts/install.sh         # checks SHA256SUMS, loads images, starts, waits until healthy
bash ./scripts/app.sh check            # "Schema OK"
bash ./scripts/app.sh flask create-user --username <name> --display-name "<Full Name>" --role SYS_ADMIN
bash ./scripts/app.sh flask seed-reference --actor <name>
```

Then, in the browser at `https://<name>`: sign in as that administrator and add the users, roles and groups in
**Settings**. Before switching to directory sign-in: follow `deployment/ldap/README.md` (CA certificate in `ldap/`,
`ldap.env`, `BREAK_GLASS_USERNAME`, `bash ./scripts/app.sh flask set-break-glass-password`). Schedule the daily jobs
(`purge-sessions`, `take-snapshot`, `run-schedules`, `backup`) with cron as `deployment/README.md` section 4 shows.

Important `app.env` facts: `APP_PROFILE=oracle`, `APP_ENV=production`, `TRUSTED_PROXY_COUNT=1` (exactly one proxy:
nginx). The **mock demo accounts are never created** outside a local demo; the first account is made with
`create-user`.

### D. Smoke test after install

- `bash ./scripts/app.sh status` shows both containers up and the app healthy; `https://<name>` shows the sign-in page
  with a valid certificate (no browser warning); `http://<name>` redirects to https.
- Sign in, open the capability position, Projects, Testing, Reports; upload a document of a few MB (checks the upload
  limit through nginx); export an Excel file; generate a report.
- `bash ./scripts/app.sh logs app` shows no errors.

## 6. nginx (the HTTPS front)

`deployment/nginx/nginx.conf`, mounted read-only into the `proxy` container:

- Port **80** only answers `301` to https; port **443** serves TLS 1.2/1.3 with `/etc/nginx/certs/server.crt` and
  `server.key` (`deployment/nginx/certs/`).
- Forwards everything to `app:8080` (the app is **not** published on the host; only nginx is).
- **Sets** (replaces, never appends) `X-Forwarded-For`, `X-Forwarded-Proto https`, `X-Forwarded-Host` and `Host`; the app
  trusts exactly one proxy (`TRUSTED_PROXY_COUNT=1`), so these headers cannot be faked by a client. The sign-in
  throttle counts failures per client address from these headers. If another proxy or load balancer is placed in
  front of nginx, `TRUSTED_PROXY_COUNT` and these headers must be revisited together.
- `client_max_body_size 21m` (documents are up to 20 MB, `document_service.MAX_BYTES`); `proxy_read_timeout 300s`
  for large exports and reports.
- Does not add security headers: the app sends its own (CSP, HSTS, frame and referrer rules).
- `server_tokens off`; no access log (the app writes its own JSON access log); errors to stderr; gzip for scripts,
  styles, JSON and SVG.
- If the company already runs its own reverse proxy instead of ours: replicate exactly the points above (TLS, header
  replacement, body size, timeouts) and keep `TRUSTED_PROXY_COUNT` equal to the number of proxies.

## 7. Updates, rollback, backups

- **Update:** build a new bundle (A); the DBA runs any **new** `oracle-scripts/V0xx` first (the commit history and
  `docs/oracle-migration.md` say which, with its grant); unpack **into the same folder** (`app.env`, `ldap.env`,
  certificates and `data/` are kept); `sudo bash ./scripts/install.sh`. The app refuses to start if the schema does not
  match; the log names what is missing.
- **Rollback:** set `APP_VERSION` in `.env` to the `# previous version` line `install.sh` wrote (that image is still
  loaded) and `bash ./scripts/app.sh restart`, only if no new database script was applied (or the DBA restored the
  database).
- **Back up:** the Oracle database (DBA: every record, the audit trail and the settings) **and** `/opt/cpc/data`
  (uploaded document files and reports; without it documents cannot be opened), plus `app.env`, `ldap.env`, `ldap/`
  and the certificate: `bash ./scripts/app.sh backup` packs those into `backups/` (copy them off the VM).

## 8. Must never happen

- No secrets in Git or in the image: `.env`, `ldap.env`, `oracle-local.env`, `app.env`, keys and certificates are
  git-ignored, kept out by `.dockerignore`, and `build.ps1` refuses a bundle that contains one.
- No demo data or mock accounts on the VM (`APP_PROFILE=demo` is for the PC only; `install.sh` refuses it).
- No internet access needed on the VM; no pulling images or packages there.
- No editing of old schema scripts: every change is a new `V0xx` pair (`db/sqlite` + `db/oracle`) plus its grant.
- More than one app process (the sign-in throttle is in memory): scale with `APP_THREADS`, not more containers.
- Never print the values of the secret files in logs, tickets or chat.

## 9. Known gaps before the first real move

1. Verified on the development PC (18 Nov 2026, Docker 29.9.3): `build.ps1` built the bundle (86 MB); the unpacked
   bundle ran under Docker Compose with nginx (HTTP → HTTPS, security headers, a 20 MB upload passes and 23 MB is
   refused, `Secure` cookie, `create-user` and `check` through `app.sh`, the sign-in limit counts per real client
   address and ignores a forged `X-Forwarded-For`). The app ran on SQLite for that test: **the Oracle profile in the
   container and `install.sh` on a real Linux VM are still to be tried** (try a Linux test VM before the real one).
2. `V007__org_units.sql` has **not been run on a real Oracle** yet: run the Oracle suite locally, and the DBA on a
   staging copy first, then `bash ./scripts/app.sh check`.
3. No load test exists for this app; agree a test window with IT before go-live (e.g. many users signing in and
   opening the dashboard at once) and watch `ORACLE_POOL_MAX` and response times.
4. `docs/LDAP_IT_MANUAL.md` still calls the system "Fleet Dashboard" in places (inherited from ship-project); its
   paths are Windows paths (in the container, see `deployment/ldap/README.md`).

## 10. Checklist for the agent doing the move

- [ ] IT/DBA values collected (`docs/IT_REQUEST.md`), VM architecture confirmed
- [ ] Section 9 gaps handled
- [ ] Unit/integration tests green; Oracle suite run locally
- [ ] `predeployment\build.ps1` produced `dist\cpc-<version>.tar.gz`; SHA-256 noted
- [ ] DBA ran `V001`–`V007` (or the new ones) and the runtime grants
- [ ] Bundle copied and unpacked on the VM; SHA-256 matches; `app.env` filled
- [ ] Certificate and key in `nginx/certs/`; DNS name matches the certificate
- [ ] `install.sh` finished healthy; `app.sh check` says Schema OK
- [ ] First SYS_ADMIN created; `seed-reference` run; break-glass admin set; directory sign-in configured (if used)
- [ ] Smoke test (section 5D) passed; daily jobs in cron; backups of Oracle and `/opt/cpc/data` confirmed with IT and the DBA
