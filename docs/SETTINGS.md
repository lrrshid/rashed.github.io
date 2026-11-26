# Settings > connections: the directory and the database from the website

For IT and system administrators. Four tabs of **Settings** (system administrators only; never in a role preview)
manage the app's connections without editing files on the server, the same way as in the Asset Availability
reference project: **Sign-in and directory**, **Database**, **Network and certificates**, **Connection history**.

## What is managed here, and what is not

| Connection | Where | Change takes effect |
|---|---|---|
| Company directory (LDAP / Active Directory) | Settings > Sign-in and directory | Within seconds |
| Sign-in method (app passwords / company directory) | Settings > Sign-in and directory | Within seconds |
| Trusted CA certificates, approved destinations | Settings > Network and certificates | Within seconds |
| A new main database (prepared, tested, staged) | Settings > Database | At the planned restart, after the server file is changed |
| The database connection, `SETTINGS_KEY`, `BREAK_GLASS_USERNAME`, capacity | The server file (`.env`, or `app.env` on the Docker VM) | At the next restart |

The database connection stays in the server file: the app needs it to load everything else.

Every connection is edited the same way: **Save draft → Test → Apply** (the database: **Stage for restart**).
Sensitive steps (apply, switch on or off, delete, a password, the sign-in method, a certificate, a destination) ask
for your password again (valid 10 minutes). Saved passwords are encrypted (AES-256-GCM) and never shown again; every
change is in **Connection history** and the audit trail, never with a password in it.

## Setting up the company directory

1. **Network and certificates**: approve each domain controller (server name, port 636 or 389, purpose *Company
   directory*), then upload the company CA certificate (`.cer`, `.crt` or `.pem`; never a private key).
2. **Sign-in and directory > Add a directory connection** (or **Import from the server file** when `ldap.env` already
   has it). Fill in the servers, encryption, CA certificate, base DN and service account; set the service account
   password. **Save draft.**
3. **Test the draft.** The stages: network and certificate, service account, search base, then optionally a sample
   username, and a test sign-in with a username and password (used once, never stored).
4. **Apply** (your password is asked again). The draft becomes active; the old revision is kept for rollback.
5. To make the directory the **sign-in method**: run a test sign-in as a system administrator on the active
   connection, then switch the method. On a server, the emergency administrator must be ready first
   (`BREAK_GLASS_USERNAME` in the server file, then `flask --app wsgi set-break-glass-password`).

Directory groups give no role: a person gets in only after an administrator adds them in Settings > Users. Plain LDAP
("LDAP (not encrypted)") is offered on purpose but sends every password in clear text; it always shows as Degraded.

## Moving to a new database (planned restart, clean start)

The database in use is shown under **Settings > Database** (read-only: type, server or file, schema, answer time,
health, and whether it holds the **demo data**). It is never changed from the website.

The new (Oracle) database **starts clean** (owner, 24 Nov 2026): the demo data, the fictional records and the
`mock.*` accounts that made them, never goes to it.

1. The DBA prepares an **empty** database: the `db/oracle` scripts up to the newest, then
   `db/oracle/runtime-grants.sql` (`docs/oracle-migration.md`). No data is copied.
2. **Network and certificates**: approve the database server (purpose *Database*).
3. **Database > Add a database connection**: server, port, service name, the app's account (not the owner), the
   owner's schema, the password. **Save draft**, then **Test**. The checks are read-only: the connection, the tables
   and their version, the permissions (every grant of `runtime-grants.sql`), and the data: a database that holds the
   demo data **fails**; an empty one passes.
4. **Stage for restart** (your password is asked again). The page then lists the steps and the lines for the server
   file; the password is never in them: type it yourself.
5. In the planned window: test again, back up, stop the app, change the server file (the database lines, and
   `SETTINGS_KEY`, which the Oracle profile needs), start the app. It checks every table, and **refuses to start on a
   database that holds the demo data**.
6. On the server: `flask --app wsgi setup-database --admin <username>` (Docker:
   `bash ./scripts/app.sh flask setup-database --admin <username>`) creates the first system administrator and the
   standard lists (groups, capability types, statuses, workflows, directorates and sections).
7. Sign in and set up the directory and the other connections again: each database keeps its own Settings.
8. To go back: put the old lines back in the server file and restart.

## Recovery (on the server)

```
cd backend
# Nobody can sign in: back to app passwords (audited as that administrator)
flask --app wsgi settings-recover --as <admin username> --sign-in local
# A connection breaks the app: switch it off (its id is in Settings)
flask --app wsgi settings-recover --as <admin username> --disable <id>
```

Every running process picks the change up within seconds. The emergency administrator can always sign in with its
own password, even when the directory is down.

## The encryption key (`SETTINGS_KEY`)

Saved passwords are encrypted with AES-256-GCM under `SETTINGS_KEY` (in the server file, never in the database). The
demo makes its own key in `data/settings.key`; the Oracle profile refuses to start without `SETTINGS_KEY`. Make one
with `python -c "import secrets,base64;print(base64.b64encode(secrets.token_bytes(32)).decode())"` (Docker VM:
`bash ./scripts/app.sh new-key`). Back it up with the server secrets: without it, saved passwords must be typed again
(the page then says "Cannot be read").

Rotation: put the new key in `SETTINGS_KEY` and the old one in `SETTINGS_KEY_PREVIOUS`, restart, run
`flask --app wsgi settings-rotate-key --as <admin username>`, then remove `SETTINGS_KEY_PREVIOUS` and restart.

## What to back up

The database (it holds the connections, their history and the encrypted passwords) and `SETTINGS_KEY`, kept
separately. A restored database with the wrong key shows its passwords as "Cannot be read".
