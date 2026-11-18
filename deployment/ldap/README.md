# Directory sign-in on the VM (optional)

Windows sign-in (`AUTH_MODE=ldap`) is set up exactly as `docs/LDAP_IT_MANUAL.md` describes, with two differences
because the app runs in a container:

1. Put the company CA certificate in **this folder** (e.g. `ldap/company-root-ca.cer`). The container sees this
   folder as `/app/ldap`, so in `ldap.env` write `LDAP_CA_FILE=/app/ldap/company-root-ca.cer`.
2. Put the directory settings in `ldap.env` **next to `docker-compose.yml`** (copy `ldap.env.example`,
   `chmod 600 ldap.env`) and set `AUTH_MODE=ldap` in it. Then `bash ./scripts/app.sh restart`.

Before switching: set `BREAK_GLASS_USERNAME` in `ldap.env`, restart, then
`bash ./scripts/app.sh flask set-break-glass-password`. Test with `bash ./scripts/app.sh flask check-ldap --username U12345`.

The VM must reach the domain controllers on 636 (ldaps) or 389 (starttls).
