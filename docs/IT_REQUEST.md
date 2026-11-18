# Request to IT and the DBA: hosting Capability Portfolio Command

The system is a web application on the company network. It needs **no internet access** at any time: it is delivered
as one file (about 150 MB) containing everything, and sends no e-mail. Please supply the items below.

## 1. Virtual machine

| Item | Value needed |
|---|---|
| Operating system | Linux 64-bit with **Docker Engine** and the **Docker Compose plugin 2.24 or newer**, installed from offline packages |
| Architecture | x86_64 or ARM (`uname -m`): tell us which |
| Size | 2 CPU cores and 4 GB RAM minimum; **4 cores and 8 GB suggested**; 20 GB disk (images, logs, uploaded documents, reports) |
| Clock | Synchronised with the company time server (NTP) |
| Folder | `/opt/cpc`, and an operator account with `sudo` for Docker |
| Backup | The folder `/opt/cpc/data` (uploaded documents and reports) and `/opt/cpc/backups` |

## 2. Network

| From → to | Port | Why |
|---|---|---|
| Users' network → VM | 443, and 80 (only redirects to 443) | The website |
| VM → Oracle | 1521 (or the DBA's TCPS port) | The database |
| VM → domain controllers | 636 (LDAPS) or 389 (StartTLS) | Windows sign-in, if used |
| DNS | — | A name for the system, e.g. `cpc.company.local`, pointing to the VM |

## 3. HTTPS certificate

For the DNS name above: `server.crt` (the certificate **followed by the intermediate chain**, PEM) and `server.key`
(PEM, no password), issued by the company CA that users' browsers already trust.

## 4. Oracle (DBA)

- A schema-owner account (e.g. `CPC_OWNER`) to run the scripts `V001`…`V007` (in the bundle under `oracle-scripts/`).
- A separate runtime account (e.g. `CPC_APP`) with only the grants in `docs/oracle-migration.md` section 3.
- The connection string `host:port/service`, and the runtime password (handed over securely, not by e-mail).
- Connections: the app keeps up to `ORACLE_POOL_MAX` (8 by default) open, plus a few for the daily jobs.
- Wallet or TCPS details, only if required.

## 5. Windows sign-in (optional, can come later)

As `docs/LDAP_IT_MANUAL.md` describes: the domain controller names, the company CA certificate, the base DN, and a
read-only service account. Until then the system uses its own passwords.

## 6. Bringing the file in

The approved way to bring one ~150 MB file into the network (USB policy or file-transfer system).
