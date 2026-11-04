# Fleet Dashboard: Windows sign-in (LDAP / Active Directory)
## Manual for the IT / directory team

**Goal:** staff sign in to the Fleet Dashboard with their normal Windows username and password (for example `U12345`).
**Your job:** give us the directory details below, put them in one file on the server, test them, then switch the sign-in on.
All names, paths and passwords in this manual are examples. Use the values from your own company.

---

## 1. What you are setting up

1. A person types their Windows username and password on the system login page.
2. The dashboard asks Active Directory: "Is this the right password for this username?"
3. If yes, the system checks its own **Settings > Users** list. Only people an ADMIN has added there, and who are still active, get in.
4. The person gets the role and departments that the ADMIN gave them in the system.

Active Directory only confirms who the person is. It does not decide who may use the system or what they can do.
A valid Windows account alone does **not** give access.

---

## 2. What we need from you (the 5 required values)

| # | Setting | What it is | What to give us | Example |
|---|---------|------------|-----------------|---------|
| 1 | `LDAP_SERVER` | Name of the domain controller. Name only, no `ldaps://`. Several can be listed, separated by commas, and the app tries them in order. | The **full name written on the server's certificate**. An IP address will fail. | `dc01.company.local,dc02.company.local` |
| 2 | `LDAP_CA_FILE` | The company CA certificate file that signed the domain controllers' certificates. | The file, saved on the system server, and its full path. `.cer`, `.crt` or `.pem` both work. | `C:\CapabilityPortfolio\certs\company-root-ca.cer` |
| 3 | `LDAP_BASE_DN` | The folder (OU) in the directory where staff accounts are. Sub-folders are searched too. | The exact Distinguished Name. For the whole domain, use the domain root. | `OU=Staff,DC=company,DC=local` |
| 4 | `LDAP_BIND_DN` | The read-only **service account** the app uses to look people up. | Its sign-in name or full DN. Read-only. **Never a Domain Admin.** | `svc-cpc@company.local` |
| 5 | `LDAP_BIND_PASSWORD` | The service account's password. | The password, handed over securely (see section 6). | (never write it in this manual) |

The app refuses to start in LDAP mode if any of these is missing or still says `<IT: fill this in ...>`.

---

## 3. Settings that normally stay as they are

| Setting | Default | Meaning |
|---------|---------|---------|
| `AUTH_MODE` | `local` | `local` = the app's own demo passwords. `ldap` = Windows sign-in. **Keep `local` until the test in step 8 passes.** |
| `LDAP_PORT` | `636` | `636` for `ldaps`, `389` for `starttls`. |
| `LDAP_SECURITY` | `ldaps` | `ldaps` = encrypted from the start. `starttls` = encrypted before any password is sent. Plain unencrypted LDAP is **not** allowed. |
| `LDAP_USERNAME_ATTRIBUTE` | `sAMAccountName` | The directory field that holds the Windows username. |
| `LDAP_DISPLAY_NAME_ATTRIBUTE` | `displayName` | The field with the person's full name, shown in the app. The app copies it again at every sign-in, so a name corrected in the directory shows from the person's next sign-in. |
| `LDAP_USERNAME_PATTERN` | `^U[0-9]+$` | Allowed username format: the letter U and digits. Upper or lower case both work. Typing `COMPANY\U12345` or `U12345@company.local` is accepted; the app removes the domain part. Tell us if your usernames look different. |
| `LDAP_TIMEOUT_SECONDS` | `5` | Seconds to wait for the directory (1 to 60) before trying the next server or giving up. |
| `SESSION_IDLE_MINUTES` | `30` | Signs a person out after this many minutes without use. |
| `SESSION_ABSOLUTE_HOURS` | `12` | Signs a person out after this many hours, even if they are active. |

---

## 4. Emergency (break-glass) administrator

A local ADMIN account for when the directory is down and nobody can sign in. Its password is kept in the app, never in the directory.

| Setting | Meaning |
|---------|---------|
| `BREAK_GLASS_USERNAME` | The account name. **Empty = no emergency account.** The owner chose `AILAB` (already in `ldap.env.example`). 2 to 120 characters: letters, digits, `.`, `_`, `-`. It must **not** look like a Windows username (U plus digits) and must **not** start with `mock.`. |

Rules for its password:
- At least **16 characters**. A passphrase works well.
- Set **only** with the command in step 7. It cannot be set or changed from the web page.
- Store it in your approved password vault. It appears nowhere else.
- Every use, successful or failed, is written to the app log as a WARNING with the client IP.
- Use it only in emergencies. Afterwards, review the log and set a new password.

---

## 5. Where settings are read from (priority)

1. Server environment variables (highest)
2. `ldap.env` (next to `README.md`)
3. `.env` (lowest)

If the effective sign-in mode is not what you expect, check that no server environment variable overrides `AUTH_MODE`.

---

## 6. Security rules

- `ldap.env` holds the service-account password. It is **not** stored in git. Restrict access to it on the server.
- Never send the password by chat or email. Hand it over in person or through your vault.
- The service account needs read access to the user accounts only.
- The server certificate must be signed by the CA in `LDAP_CA_FILE`, and its name must match `LDAP_SERVER`. The app always checks both.
- Passwords are never written to logs.

---

## 7. Step-by-step procedure

All commands run in PowerShell on the system server.

**Step 1. Collect the values (IT / directory admin).** Fill in the 5 required values in section 2. Place the CA certificate file on the server.

**Step 2. Create the settings file.** In the project folder (next to `README.md`), copy `ldap.env.example` to `ldap.env`.

```powershell
Copy-Item ldap.env.example ldap.env
```

**Step 3. Fill in `ldap.env`.** Replace every `<IT: fill this in ...>` with the real value. Remove the `< >` too.
- One setting per line, `NAME=value`, with no spaces around `=`.
- If the password contains `#`, a space or a quote, wrap it in single quotes: `LDAP_BIND_PASSWORD='my#pass word'`.
- Leave `AUTH_MODE=local` for now.

**Step 4. Test the directory (nothing is switched on yet).**

```powershell
cd backend
..\.venv\Scripts\python.exe -m flask --app wsgi check-ldap --username U12345
```

Use a real Windows username instead of `U12345`. Every line must say OK:

| Check | If it fails, look at |
|-------|----------------------|
| Server reachable, certificate trusted | `LDAP_SERVER` spelling, `LDAP_PORT`, firewall, `LDAP_CA_FILE`, certificate name |
| Service account signs in | `LDAP_BIND_DN`, `LDAP_BIND_PASSWORD`, account locked, disabled or expired |
| Search folder found | `LDAP_BASE_DN` |
| Test user found, display name shown | `LDAP_BASE_DN`, `LDAP_USERNAME_ATTRIBUTE`, `LDAP_USERNAME_PATTERN` |

Fix and repeat until all checks pass.

**Step 5. Create the emergency account (recommended).** `ldap.env` already has `BREAK_GLASS_USERNAME=AILAB` (the owner's choice). Ask the owner for the password (never written in any file), then:

```powershell
..\.venv\Scripts\python.exe -m flask --app wsgi set-break-glass-password
```

Type a password of at least 16 characters when asked. Save it in the vault.

**Step 6. Add the first users (system administrator).** On the **Settings > Users** page, add each person by Windows username, with their role and departments. Nobody can sign in who is not added and active here.

**Step 7. Switch it on.** In `ldap.env` change `AUTH_MODE=local` to `AUTH_MODE=ldap`. Save, then restart the system.

**Step 8. Verify.**
1. An added employee signs in with their Windows username and password. This should work.
2. A Windows user who was **not** added should be refused.
3. A wrong password should be refused.
4. Check that the role and departments are right for the employee.
5. Test the emergency account once and confirm the WARNING line in the log.
6. Look through the application log for errors.
7. Confirm the session timeouts (30 minutes idle, 12 hours total).

---

## 8. Good to know

- **Directory outage:** if the directory cannot be reached, people see "The company directory cannot be reached". The emergency account still works.
- **Disabled accounts:** if IT disables someone in Active Directory, they can no longer sign in. A session they already have open lasts until the 12-hour limit, unless a system administrator deactivates them in Settings > Users, which ends it at once.
- **Unclear matches:** if a username matches no account, or more than one, the sign-in is refused.
- **Empty passwords:** blank passwords are refused before the directory is asked.
- **Diagnosing problems:**
  - Login works in the test but not in the app: check that the person is added and active in Settings > Users.
  - The app still uses local login: check for a server environment variable that overrides `AUTH_MODE`, and restart the app.

---

## 9. Final checklist

- [ ] Real server name(s) confirmed (the name on the certificate)
- [ ] CA certificate file on the server, path in `LDAP_CA_FILE`
- [ ] Real Base DN confirmed
- [ ] Read-only service account created, password handed over securely
- [ ] Username attribute and pattern match your account format
- [ ] `check-ldap` reports every check OK
- [ ] Emergency account created, password in the vault, and tested
- [ ] First users added in Settings > Users
- [ ] `AUTH_MODE=ldap` set and app restarted
- [ ] Authorised and unauthorised sign-ins tested
- [ ] `ldap.env` is not in git and access to it is restricted
