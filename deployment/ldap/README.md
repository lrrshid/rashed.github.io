# Directory sign-in on the VM (optional)

The simplest way is the website: **Settings > Sign-in and directory** (system administrators; `docs/SETTINGS.md`):
enter the domain controllers, the CA certificate, the base DN and the service account, test, apply, then switch the
sign-in method. Nothing to restart.

The older way, with a file, as `docs/LDAP_IT_MANUAL.md` describes, with two differences because the app runs in a
container:

1. Put the company CA certificate in **this folder** (`/opt/cpc/ldap/`, e.g. `company-root-ca.cer`). The container
   sees it as `/app/ldap`, so in `ldap.env` write `LDAP_CA_FILE=/app/ldap/company-root-ca.cer`.
2. Put the directory settings in `/opt/cpc/ldap.env` (copy `ldap.env.example`, `chmod 600 ldap.env`) with
   `AUTH_MODE=ldap`, then `sudo /opt/cpc/install.sh` (it starts the app with ldap.env).

Before switching: set `BREAK_GLASS_USERNAME` in `ldap.env`, then
`/opt/cpc/scripts/app.sh flask set-break-glass-password`. Test with
`/opt/cpc/scripts/app.sh flask check-ldap --username U12345`.

The VM must reach the domain controllers on 636 (ldaps) or 389 (starttls).
