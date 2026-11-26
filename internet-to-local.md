# Internet to local: moving Capability Portfolio Command to the company's local VM

**Audience:** an agent (or engineer) asked to deploy or update this project on the company's **offline local
virtual machine**. Read this file first; it lists every piece, where it lives in the repository, what IT and the DBA
must supply, and the exact order of work. The detailed guides it points to stay the source of truth for their topic.

## 1. The situation in one paragraph

The project is developed on an **internet-connected Windows PC** (this repository, Docker Desktop, Python, Git). The
target is a **Linux VM on the company network with no internet, with Docker and its own nginx**. The VM never
downloads anything: on the internet-connected PC we build a **Docker image** of the app and pack it, with the nginx
image (only for a VM without nginx) and the deployment files, into **one `.tar.gz` kit**. That one file is carried to the
VM, unpacked, and installed by **one command, `sudo ./install.sh`**, which asks four questions and does the rest: the
app runs in one container on `127.0.0.1:8770`, the VM's nginx serves it over HTTPS. The records live in the built-in
database (a file in `/opt/cpc/data`) or in the company's **Oracle**; uploaded scans and reports live in `/opt/cpc/data`.

```
 Internet PC (Windows)                         Company network (offline)
 ────────────────────────                      ───────────────────────────────────────────────────────
 repo ─▶ tests ─▶ predeployment/build.ps1      Local VM (Linux, Docker, nginx)
               │  docker build (Dockerfile)      nginx (the VM's) :443 HTTPS, :80 → 443   site conf.d/cpc.conf
               │  test start on :18080             └─▶ 127.0.0.1:8770 ─▶ container cpc-app (cpc:<version>)
               │  docker save (app, nginx)                                ├─▶ /opt/cpc/data (database file, scans,
               │  pack.py (Linux permissions)                             │    reports) and /opt/cpc/app.env
               ▼                                                          ├─▶ Oracle (optional; DBA; schema V001–V011)
   dist/cpc-<version>.tar.gz ──────────────────▶                          └─▶ LDAP / AD (optional, from Settings)
                 (one file, ~150 MB)
```

## 2. What exists in the repository

| Path | Used on | What it is |
|---|---|---|
| `predeployment/Dockerfile` | internet PC | The app image: `python:3.12.10-slim-bookworm`, installs `backend/requirements.txt` (pinned by `constraints.txt`), copies `backend/` (no tests), `frontend/`, `db/`; runs as user `app` (uid 10001); only `/app/data` is writable; `HEALTHCHECK` on `/api/v1/health`; `CMD python serve.py` |
| `predeployment/build.ps1` | internet PC | Builds the kit: tests → `docker build` → a test start on port 18080 (read-only, health + page + script + security headers) → `docker pull nginx:1.27.3-alpine` → assembles `dist\cpc-<version>\` → `docker save` both images → LF line endings → `IMAGE_PLATFORM` → `SHA256SUMS` → `pack.py`. `-Platform linux/arm64` for an ARM VM |
| `predeployment/pack.py` | internet PC | Packs the kit with Linux permissions (every `*.sh` executable), so `./install.sh` runs straight after `tar -xzf` |
| `.dockerignore` | internet PC | Allow-list: only `backend/` (minus tests and dev files), `frontend/`, `db/`; never secrets or `data/` |
| `backend/serve.py` | image | The production server: waitress, **one process**, `APP_THREADS` threads (default 8), `APP_LISTEN`. Behind a proxy (`TRUSTED_PROXY_COUNT` > 0) it lets the `X-Forwarded-*` headers through to ProxyFix |
| `deployment/install.sh` | VM | **The one command**: checks the VM and `SHA256SUMS`, loads the image, installs into `/opt/cpc`, writes `app.env` on a first install (built-in database or Oracle, a new `SETTINGS_KEY`), the certificate (IT's or self-signed), starts `cpc-app` (read-only, `cap-drop ALL`, `no-new-privileges`, port on `127.0.0.1` only), adds the nginx site (checked with `nginx -t`, then reloaded; SELinux handled), checks the site through nginx, creates the first administrator (`setup-database --password-stdin`), installs `/etc/cron.d/cpc`. Repeatable: an update takes a backup first and keeps the settings and the data |
| `deployment/scripts/app.sh` | VM | Everyday commands: `status`, `start`, `stop`, `restart`, `logs`, `wait`, `check` (schema), `version`, `url`, `flask <command>`, `backup` (a consistent copy of the built-in database + scans + reports + settings, kept 14 days), `new-key` |
| `deployment/nginx/cpc-site.conf.template` | VM | The site added to the VM's nginx (section 6) |
| `deployment/nginx/nginx.conf` | VM | Only for a VM without nginx: the bundled nginx container (`cpc-proxy`) |
| `deployment/app.env.example` | VM | Every setting explained (both database blocks) |
| `deployment/certs/README.md` | VM | IT's certificate and key (`server.crt`, `server.key`); else a self-signed one |
| `deployment/ldap/README.md` | VM | Directory sign-in the file way (the website way: Settings > Sign-in and directory) |
| `deployment/README.md`, `deployment/README-AR.md` | VM | The install guide inside the kit (English for IT; Arabic quick guide) |
| `db/oracle/V001__schema.sql` … `V011__action_log.sql` | DBA | The Oracle schema scripts, run in order by the DBA (bundled as `oracle-scripts/`) |
| `db/oracle/runtime-grants.sql` | DBA | The runtime account's grants (bundled too); Settings > Database checks a new database against it |
| `docs/oracle-migration.md` | DBA | Run order, grants, the clean start (`setup-database`), Oracle specifics |
| `docs/SETTINGS.md` | IT | Settings > connections: the directory and the database from the website, `SETTINGS_KEY`, recovery |
| `docs/IT_REQUEST.md` | IT | Everything to ask IT and the DBA for (VM, network, certificate, Oracle, directory, file transfer) |
| `docs/LDAP_IT_MANUAL.md`, `docs/LDAP_SETUP.txt`, `ldap.env.example` | IT | Directory sign-in |
| `backend/tests/oracle` | internet PC | The Oracle suite: applies the scripts to throwaway accounts on a real Oracle and runs the app as the restricted runtime account |
| `backend/tests/unit/test_deployment.py` | internet PC | Keeps these files consistent: Oracle scripts named in the guides, both nginx configurations admit the upload limit and set the forwarded headers, every template placeholder is filled, the app is published on the loopback only, nothing is downloaded on the VM, no password on a command line, the kit keeps its scripts executable |
| `dist/` | internet PC | Where kits are written (git-ignored; never committed) |

## 3. Requirements

### 3.1 The internet-connected PC (build machine)

- Windows 10/11 with **Docker Desktop** (Linux containers) running, **Git**, **Python 3.12** with the project's `.venv`
  (made by `scripts\run_dev.ps1`).
- Internet access to: Docker Hub (`python:3.12.10-slim-bookworm`, `nginx:1.27.3-alpine`) and PyPI (the pinned
  packages, fetched inside the image build).
- About 2 GB free for the images and the kit.
- **CPU architecture must match the VM.** Default `linux/amd64`; for an ARM VM (`aarch64`) run
  `build.ps1 -Platform linux/arm64`. `install.sh` refuses a kit built for another CPU type.

### 3.2 The local VM

- Linux 64-bit with **Docker Engine** running (`docker info`) and **nginx** (any version from 1.14; `nginx -v`).
  **No Docker Compose needed.** Without nginx, `install.sh` runs the bundled nginx container instead.
- At least 2 CPU cores and 4 GB RAM; **4 cores and 8 GB suggested**. Disk: the image, logs (rotated at 10 × 20 MB),
  the database file, the uploaded scans (up to 20 MB each), reports and 14 days of backups in `/opt/cpc`.
- **Time synchronised (NTP)**: sign-in sessions depend on it.
- `sha256sum`, `tar`, `bash`, `openssl` (standard); `curl` for the final check.

### 3.3 Network (ask IT to open)

| From → To | Port | Why |
|---|---|---|
| Users' network → VM | 443 (and 80, which only redirects) | The website |
| VM → Oracle (if used) | usually 1521 (or the DBA's TCPS port) | The database |
| VM → domain controllers | 636 (LDAPS) or 389 (StartTLS) | Directory sign-in, if used |
| DNS | — | A name for the app (e.g. `cpc.company.local`) pointing to the VM (or users type its IP) |

The app makes no other outbound connection: no e-mail, no internet, no CDN.

## 4. What IT and the DBA supply

Use `docs/IT_REQUEST.md` as the form. Nothing is needed to start (built-in database, self-signed certificate,
the app's own passwords); for the full set-up:

1. **Certificate (IT):** `server.crt` (for the app's DNS name **followed by the intermediate chain**, PEM) and
   `server.key` (PEM, no password).
2. **DNS name** for the app; users open `https://<name>`, which must match the certificate.
3. **Oracle (DBA), when the records move there:** the DSN (`host:port/service`), a schema-owner account (e.g.
   `CPC_OWNER`) and a separate runtime account (e.g. `CPC_APP`) with its password; the DBA runs `V001`–`V011` as the
   owner on an **empty** schema, then the runtime grants (`docs/oracle-migration.md`).
4. **Sign-in:** Active Directory over LDAP (`docs/LDAP_IT_MANUAL.md`), entered in Settings; a username for the
   **emergency (break-glass) administrator** (`BREAK_GLASS_USERNAME`).
5. **The approved way to bring a file into the network** and its size limit (the kit is about 150 MB).

## 5. Step by step

### A. On the internet-connected PC

1. `git pull`; make sure the work is committed (the version becomes `yyyy.MM.dd-<commit>`; uncommitted work gets
   `-dirty`).
2. Start Docker Desktop, then build: `powershell -ExecutionPolicy Bypass -File predeployment\build.ps1` (it runs the
   tests first; `-SkipTests` only if they just passed). Result: `dist\cpc-<version>.tar.gz`.
3. Recommended before Oracle: the **Oracle suite** against a local Oracle (`docs/oracle-migration.md` section 8).
   `V001`–`V006` were verified on Oracle Database 26ai Free (5 Nov 2026); **`V007` (org units), `V008` (golden
   samples, attachments), `V009` (Settings connections), `V010` (role levels, records.change) and `V011` (user
   tracking) have not yet run on a real Oracle**.
4. Note the file's SHA-256 (printed by the script).

### B. Carry the kit

Copy the single `.tar.gz` through the approved channel. Never copy `.env`, `ldap.env`, `oracle-local.env`, `data\` or
any key: the kit deliberately contains none of them (`build.ps1` refuses to build if one slips in).

### C. On the VM

```bash
sha256sum cpc-<version>.tar.gz          # must equal the value noted in A
tar -xzf cpc-<version>.tar.gz && cd cpc-<version>
# optional: cp server.crt server.key certs/     (IT's certificate; else a self-signed one is made)
sudo ./install.sh
```

It asks the name users type, the database (built-in or Oracle), the first administrator's username and password.
`deployment/README.md` (inside the kit) explains every step, the `--yes` mode, ports, updates and recovery.

Then, in the browser: sign in as that administrator and add the people in **Settings > Users** (or Import from Excel).
Directory sign-in: Settings > Sign-in and directory (`docs/SETTINGS.md`); add your own Windows account as
administrator before switching.

### D. Smoke test after install

- `install.sh` ended with "Checked: https://<name>/ answers through nginx"; `app.sh status` shows `cpc-app` healthy.
- `https://<name>` shows the sign-in page (a browser warning only with the self-signed certificate); `http://<name>`
  redirects to https.
- Sign in, add a person, open the capability position, Projects, Reports; upload a scan of a few MB (the upload limit
  through nginx); export an Excel file; **User tracking** lists these actions.
- `app.sh logs` shows no errors; `app.sh backup` writes a file in `/opt/cpc/backups`.

## 6. nginx (the HTTPS front)

On a VM with nginx, `install.sh` writes `conf.d/cpc.conf` (or `http.d/` on Alpine; the folder nginx's `http` block
includes) from `nginx/cpc-site.conf.template`:

- Port **80** only answers `301` to https; the HTTPS port (443 by default) serves TLS 1.2/1.3 with
  `/opt/cpc/certs/server.crt` and `server.key`. Both server blocks answer only to the chosen name, so other sites of
  the VM's nginx are untouched.
- Forwards everything to `127.0.0.1:8770` (the app is **not** reachable from the network; only nginx is).
- **Sets** (replaces, never appends) `X-Forwarded-For`, `X-Forwarded-Proto https`, `X-Forwarded-Host` and `Host`; the
  app trusts exactly one proxy (`TRUSTED_PROXY_COUNT=1`), so these headers cannot be faked by a client. The sign-in
  throttle counts failures per client address from these headers.
- `client_max_body_size 21m` (scans are up to 20 MB); `proxy_read_timeout 300s` for large exports and reports.
- Works with old nginx (no `http2` directive; its own SSL cache zone name). The app sends its own security headers.
- A refused configuration (`nginx -t`) is removed and nginx is left as it was; SELinux (RHEL family): `install.sh`
  sets `httpd_can_network_connect`.
- Without nginx on the VM: the bundled `nginx:1.27.3-alpine` container (`cpc-proxy`, `nginx/nginx.conf`) does the same
  on ports 443 and 80.

## 7. Updates, rollback, backups

- **Update:** build a new kit (A); with Oracle, the DBA runs any **new** `oracle-scripts/V0xx` first; unpack the new kit
  anywhere and run its `sudo ./install.sh`. It takes a backup, keeps `/opt/cpc/app.env`, `data/` and `certs/`, loads
  the new image and restarts the app. The app refuses to start if the schema does not match; the log names what is
  missing.
- **Rollback:** the previous image stays loaded. Stop the app, restore the backup taken just before the update
  (`tar -xzf /opt/cpc/backups/cpc-<date>.tar.gz -C /opt/cpc`), run the previous kit's `install.sh`.
- **Back up:** `app.sh backup` (also nightly at 02:00 by `/etc/cron.d/cpc`) packs the built-in database (a consistent
  copy), the scans, reports, `app.env` (with `SETTINGS_KEY`) and the certificate into `/opt/cpc/backups`; copy them off
  the VM. With Oracle, the DBA backs up the records.

## 8. Must never happen

- No secrets in Git or in the image: `.env`, `ldap.env`, `oracle-local.env`, `app.env`, keys and certificates are
  git-ignored, kept out by `.dockerignore`, and `build.ps1` refuses a kit that contains one.
- No demo data or mock accounts on the VM: `APP_ENV=production` makes the built-in database start empty (roles only;
  `setup-database` adds the first administrator and the standard lists) and refuses `mock.*` names; Oracle refuses to
  start on demo data.
- No internet access needed on the VM; no pulling images or packages there.
- No editing of old schema scripts: every change is a new `V0xx` pair (`db/sqlite` + `db/oracle`) plus its grant.
- More than one app process (the sign-in throttle is in memory): scale with `APP_THREADS`, not more containers.
- Never print the values of the secret files in logs, tickets or chat.

## 9. Known gaps before the first real move

1. The kit of 25 Nov 2026 was installed with `install.sh` in a Linux container standing in for the VM (Docker inside,
   nginx installed, no network to the outside for the install): see the README's handover notes for what was
   checked. A **real Linux VM** has not been tried yet: try a test VM before the real one.
2. `V007__org_units.sql` to `V011__action_log.sql` have **not been run on a real Oracle** yet: run the Oracle suite
   locally, and the DBA on a staging copy first, then `app.sh check`.
3. No load test exists for this app; agree a test window with IT before go-live and watch response times (and
   `ORACLE_POOL_MAX` with Oracle).
4. `docs/LDAP_IT_MANUAL.md` still calls the system "Fleet Dashboard" in places (inherited from ship-project); its
   paths are Windows paths (in the container, see `deployment/ldap/README.md`).

## 10. Checklist for the agent doing the move

- [ ] VM: Docker running, nginx present (or not: the bundled one), CPU type confirmed
- [ ] Section 9 gaps handled
- [ ] `predeployment\build.ps1` (tests included) produced `dist\cpc-<version>.tar.gz`; SHA-256 noted
- [ ] With Oracle: the DBA ran `V001`–`V011` and `runtime-grants.sql` on an empty schema
- [ ] Kit copied and unpacked on the VM; SHA-256 matches; IT's certificate in `certs/` (or self-signed accepted)
- [ ] `install.sh` finished with "answers through nginx"; `app.sh check` says Schema OK
- [ ] First administrator signs in; break-glass admin set and directory sign-in configured (if used)
- [ ] Smoke test (section 5D) passed; daily jobs in `/etc/cron.d/cpc`; backups copied off the VM
