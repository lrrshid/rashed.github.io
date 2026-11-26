# Capability Portfolio Command: install on the offline VM

This folder is the unpacked kit `cpc-<version>.tar.gz`, built on the internet-connected PC by
`predeployment\build.ps1`. Nothing here downloads anything: the application image is in `images/`.
Arabic quick guide: `README-AR.md`.

```
 Users' browsers ──HTTPS──▶ the VM's nginx (site cpc.conf) ──▶ 127.0.0.1:8770 ──▶ container cpc-app (cpc:<version>)
                                                                                     ├─▶ /opt/cpc/data (database file,
                                                                                     │    uploaded scans, reports)
                                                                                     ├─▶ Oracle (optional, DBA)
                                                                                     └─▶ domain controllers (optional)
```

| Path | What it is |
|---|---|
| `install.sh` | **The one command**: first install, update, or apply a change (certificate, ldap.env) |
| `scripts/app.sh` | Everyday commands: status, logs, restart, backup, check, flask ... |
| `nginx/cpc-site.conf.template` | The site `install.sh` adds to the VM's nginx |
| `nginx/nginx.conf` | Only for a VM without nginx: the bundled nginx container uses it |
| `app.env.example` | Every setting explained (`install.sh` writes `/opt/cpc/app.env`) |
| `certs/README.md` | IT's HTTPS certificate (else `install.sh` makes a self-signed one) |
| `ldap.env.example`, `ldap/README.md` | Windows (directory) sign-in the old way; the website way is Settings |
| `images/` | The application image, and nginx for a VM without nginx (`docker load`) |
| `oracle-scripts/` | The schema scripts `V001`…`V011` for the DBA, in order, and `runtime-grants.sql` |
| `docs/` | `SETTINGS.md` (directory and database from the website), `oracle-migration.md`, `IT_REQUEST.md`, LDAP guides |
| `VERSION`, `IMAGE_PLATFORM`, `SHA256SUMS` | The version, the CPU type, and the checksums `install.sh` verifies |

## 1. Before you start

- A Linux VM (x86-64 unless the kit was built for ARM) with **Docker Engine** running (`docker info`) and
  **nginx** (`nginx -v`). No Docker Compose is needed. Without nginx, `install.sh` runs the bundled nginx container.
- `openssl`, `sha256sum`, `tar` (present on every usual distribution); `curl` lets `install.sh` check the site at the
  end.
- Root (`sudo`).
- Users reach the VM on 443 (and 80, which only redirects to HTTPS). The VM's clock is synchronised (NTP).
- Optional: IT's certificate for the name users will type (`certs/README.md`). Without it the site starts with a
  self-signed certificate (browsers warn) that can be replaced later.
- Optional, for Oracle instead of the built-in database: the DBA has run `oracle-scripts/V001`…`V011` on an **empty**
  schema, then `runtime-grants.sql` (`docs/oracle-migration.md`). The demo data never goes to Oracle: the app refuses
  to start on a database that holds it.

## 2. Install

```bash
sha256sum cpc-<version>.tar.gz          # the same value as printed when the kit was built
tar -xzf cpc-<version>.tar.gz
cd cpc-<version>
sudo ./install.sh
```

It asks four things (Enter keeps the value in brackets):

1. **The name users type in the browser**: the VM's DNS name or its IP address.
2. **The database**: `1` built-in (a file in `/opt/cpc/data`; start now, move to Oracle later from Settings >
   Database) or `2` Oracle (address `host:port/service`, account, schema, password).
3. **The first system administrator's username** (e.g. a U number).
4. **Their password** (twice, not shown).

Then it loads the image, writes `/opt/cpc/app.env` (with a new `SETTINGS_KEY`), makes the certificate, starts the
app container on `127.0.0.1:8770`, adds `cpc.conf` to nginx's `conf.d` (checked with `nginx -t` first: a refused
configuration is removed and nginx is left as it was), reloads nginx, checks the site through nginx, creates the
administrator and the standard lists, and installs the daily jobs (`/etc/cron.d/cpc`). It ends with the address.

Without questions (all values from the environment; see the top of `install.sh` for the list):

```bash
sudo CPC_SERVER_NAME=cpc.company.local CPC_DB=builtin CPC_ADMIN=U12345 CPC_ADMIN_PASSWORD='...' ./install.sh --yes
```

Different ports: `CPC_HTTPS_PORT=8443` (the site), `CPC_APP_PORT=8770` (the app on the loopback, for nginx).

## 3. After the install

- Open the address, sign in as the administrator, then add people: Settings > Users (one by one, or **Import from
  Excel**). The roles are the organisation's structure (commander, heads of section, project manager, user).
- Windows sign-in: Settings > **Sign-in and directory** (`docs/SETTINGS.md`). Before switching, add your own Windows
  account as system administrator: the local `admin` password stops working.
- Moving to Oracle later: Settings > **Database** (test an empty Oracle, stage it), then the Oracle block of
  `/opt/cpc/app.env` and `sudo /opt/cpc/scripts/app.sh restart`, then `app.sh flask setup-database --admin <name>`.

## 4. Everyday

```bash
sudo /opt/cpc/scripts/app.sh status       # containers, version, address
sudo /opt/cpc/scripts/app.sh logs         # the app's log (Ctrl+C to stop)
sudo /opt/cpc/scripts/app.sh restart      # after changing app.env or ldap.env
sudo /opt/cpc/scripts/app.sh backup       # into /opt/cpc/backups (also every night at 02:00), kept 14 days
sudo /opt/cpc/scripts/app.sh check        # every table and column the app needs is there
```

**Backups**: `/opt/cpc/backups/cpc-<date>.tar.gz` holds the database (built-in; a consistent copy taken while the app
runs), the uploaded scans, the scheduled reports, `app.env` (with `SETTINGS_KEY`) and the certificate. Copy them off
the VM. With Oracle, the records are in Oracle: the DBA backs them up.

**Daily jobs** (`/etc/cron.d/cpc`, log `/var/log/cpc-jobs.log`): the KPI snapshot (01:15), the scheduled reports
(01:30), old sessions (01:45), the backup (02:00). Without `/etc/cron.d`, put these lines in root's crontab.

## 5. Update

Copy the new kit, unpack it anywhere, run its `install.sh`. It takes a backup first, keeps `/opt/cpc/app.env`, the data
and the certificate, loads the new image and restarts the app (a minute without service). Schema changes are applied
by the app at start (built-in database) or by the DBA first (Oracle: the new `oracle-scripts`).

To go back: the previous version's image stays loaded. Restore the backup taken just before the update
(`tar -xzf ... -C /opt/cpc` with the app stopped), then run the previous kit's `install.sh`.

## 6. If something goes wrong

| Symptom | Look at |
|---|---|
| `install.sh` stops with ERROR | The message says what to fix; run it again (it is safe to repeat) |
| The site answers 502 | `app.sh status`, `app.sh logs`; on RHEL-family VMs SELinux: `getsebool httpd_can_network_connect` (install.sh sets it) |
| The browser warns about the certificate | The self-signed one: put IT's in `/opt/cpc/certs/` (`certs/README.md`), `sudo /opt/cpc/install.sh` |
| Nobody can sign in after switching to Windows sign-in | `app.sh flask settings-recover --as <admin> --sign-in local` (`docs/SETTINGS.md`) |
| Port 443 is taken by another program (not nginx) | `sudo CPC_HTTPS_PORT=8443 ./install.sh`; open `https://<name>:8443/` |
