# Capability Portfolio Command: install on the offline VM

This folder is the unpacked bundle `cpc-<version>.tar.gz`, built on the internet-connected PC by
`predeployment\build.ps1`. Nothing here downloads anything: both images are in `images/`.

```
 Users' browsers ──HTTPS 443──▶ proxy (nginx:1.27.3-alpine) ──▶ app (cpc:<version>, waitress :8080)
                                                                   ├─▶ Oracle (DBA)
                                                                   └─▶ domain controllers (optional, ldap.env)
```

| Path | What it is |
|---|---|
| `docker-compose.yml` | The two containers. Needs **Docker Compose 2.24+** |
| `app.env.example` | The settings template → `app.env` (yours, never in the bundle) |
| `ldap.env.example`, `ldap/README.md` | Windows (directory) sign-in, optional |
| `nginx/nginx.conf`, `nginx/certs/README.md` | The HTTPS front; IT's certificate goes in `nginx/certs/` |
| `scripts/install.sh` | First install and every update |
| `scripts/app.sh` | Everyday commands |
| `images/` | The two Docker images (`docker load`) |
| `oracle-scripts/` | The schema scripts `V001`…`V007` for the DBA, in order |
| `docs/` | `oracle-migration.md` (DBA: run order and runtime grants), `IT_REQUEST.md`, `LDAP_IT_MANUAL.md` |
| `data/` | Made by `install.sh`: uploaded document files and scheduled reports. **Back it up** |
| `VERSION`, `SHA256SUMS` | The version, and the checksums `install.sh` verifies |

## 1. Before you start

- Docker Engine and the Compose plugin 2.24+ (`docker compose version`), installed offline by IT.
- The DBA has run `oracle-scripts/V001`…`V007` as the owner account (e.g. `CPC_OWNER`) and the runtime grants of
  `docs/oracle-migration.md` section 3 for the runtime account (e.g. `CPC_APP`).
- IT's certificate (`server.crt` with its chain, `server.key`) for the app's DNS name.
- The VM reaches Oracle (usually 1521) and users reach the VM on 443 (and 80, which only redirects).
- The VM's clock is synchronised (NTP): sign-in sessions depend on it.

## 2. First install

```bash
mkdir -p /opt/cpc && cd /opt/cpc
tar -xzf /path/to/cpc-<version>.tar.gz --strip-components=1
sha256sum /path/to/cpc-<version>.tar.gz          # compare with the value noted on the build PC
cp app.env.example app.env && chmod 600 app.env
nano app.env                                     # fill every <...>: ORACLE_DSN, ORACLE_PASSWORD, ...
cp /path/to/server.crt /path/to/server.key nginx/certs/
sudo bash ./scripts/install.sh                   # checks, loads the images, starts, waits until healthy
bash ./scripts/app.sh check                      # "Schema OK"
bash ./scripts/app.sh flask create-user --username <name> --display-name "<Full Name>" --role SYS_ADMIN
bash ./scripts/app.sh flask seed-reference --actor <name>     # the starting lists (groups, categories, statuses ...)
```

Then open `https://<name>` and sign in as that administrator: add the users, their roles and groups in
**Settings**. The demo accounts (`mock.*`) never exist here.

On a VM with SELinux enforcing (Red Hat family), add `:z` to the two `volumes` lines of the `app` service in
`docker-compose.yml` if the app cannot write `data/` or read `ldap/`.

## 3. Windows (directory) sign-in

See `ldap/README.md`: the CA certificate goes in `ldap/`, the settings in `ldap.env`, and
`bash ./scripts/app.sh flask set-break-glass-password` is run before the switch.

## 4. Daily jobs

As root, `crontab -e`:

```
15 1 * * * cd /opt/cpc && bash ./scripts/app.sh flask purge-sessions  >> /var/log/cpc-jobs.log 2>&1
30 1 * * * cd /opt/cpc && bash ./scripts/app.sh flask take-snapshot   >> /var/log/cpc-jobs.log 2>&1
45 1 * * * cd /opt/cpc && bash ./scripts/app.sh flask run-schedules   >> /var/log/cpc-jobs.log 2>&1
30 2 * * * cd /opt/cpc && bash ./scripts/app.sh backup                >> /var/log/cpc-jobs.log 2>&1
```

`take-snapshot` stores the day's KPI values (the month / quarter / year trends); `run-schedules` writes the
scheduled reports into `data/reports/` (also downloadable from Reports > Report history); `backup` packs `data/` and
the settings into `backups/` (copy them off the VM; delete old ones).

## 5. Smoke test

- `bash ./scripts/app.sh status`: both containers `healthy` / `running`.
- `https://<name>` shows the sign-in page with no certificate warning; `http://<name>` redirects to https.
- Sign in; open the capability position, Projects, Testing, Reports; upload a document of a few MB (checks the
  upload limit through nginx); export an Excel file; generate a report.
- `bash ./scripts/app.sh logs app` shows no errors.

## 6. Updates and rollback

- **Update:** the DBA first runs any **new** `oracle-scripts/V0xx` (and its grant from `docs/oracle-migration.md`).
  Then unpack the new bundle **into the same folder** (`app.env`, `ldap.env`, `nginx/certs/`, `data/` are kept) and
  `sudo bash ./scripts/install.sh`. The app refuses to start while the schema does not match; its log names what is
  missing (`bash ./scripts/app.sh logs app`).
- **Rollback:** only if no new database script was applied (or the DBA restored the database): in `.env` set
  `APP_VERSION` to the `# previous version` written there, then `bash ./scripts/app.sh restart`.

## 7. Back up

- Oracle (the DBA): every record, the audit trail and the settings.
- `data/`: the uploaded document files (`data/files/`) and scheduled reports. Without it, documents cannot be opened.
- `app.env`, `ldap.env`, `ldap/`, `nginx/certs/`: `bash ./scripts/app.sh backup` packs all of these.

## 8. Never

- Never put `app.env`, `ldap.env`, keys or backups in Git, tickets or chat; never print their values.
- Never run the demo profile (`APP_PROFILE=demo`) or the mock accounts here.
- Never download images or packages on the VM; a new version always comes as a new bundle.
