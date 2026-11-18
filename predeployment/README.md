# Building the offline bundle (internet-connected PC)

The full move is described in `internet-to-local.md` at the repository root; this is the build checklist.

**Needs:** Windows 10/11, **Docker Desktop** (Linux containers, running), Git, Python 3.12 with the project's `.venv`
(`scripts\run_dev.ps1` makes it), internet access to Docker Hub (`python:3.12.10-slim-bookworm`, `nginx:1.27.3-alpine`)
and PyPI, about 2 GB free.

1. `git pull`; commit your work (the version is `yyyy.MM.dd-<commit>`; uncommitted work is marked `-dirty`).
2. Start Docker Desktop.
3. `powershell -ExecutionPolicy Bypass -File predeployment\build.ps1`
   - `-SkipTests` only if `scripts\run_tests.ps1` has just passed.
   - `-Platform linux/arm64` if IT says the VM is ARM (`uname -m` prints `aarch64`); the default is x86_64.
4. Result: `dist\cpc-<version>.tar.gz` (git-ignored). Note the SHA-256 the script prints.

What the script checks on its own: the tests, that the image starts with a read-only filesystem and answers health,
the page, a script and the security headers, and that no secret file (`.env`, `app.env`, `ldap.env`, keys,
certificates) is in the bundle.

| File | Role |
|---|---|
| `Dockerfile` | The app image: Python 3.12.10 slim, the pinned runtime packages, `backend/`, `frontend/`, `db/`; user `app` (uid 10001); only `/app/data` writable; health check on `/api/v1/health`; `python serve.py` (waitress) |
| `build.ps1` | The steps above |
| `../.dockerignore` | Lets only `backend/` (without tests), `frontend/` and `db/` into the image |
| `../deployment/` | What goes to the VM (compose, nginx, scripts, settings template, install guide) |
