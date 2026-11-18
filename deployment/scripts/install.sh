#!/usr/bin/env bash
# First install or update of Capability Portfolio Command on the offline VM. Run from the unpacked bundle folder:
#   sudo bash ./scripts/install.sh
# Checks the files (SHA256SUMS), loads the two images (nothing is downloaded), checks app.env and the certificate,
# writes .env (APP_VERSION), starts both containers and waits until the app is healthy.
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"
APP_UID=10001

fail() { echo "ERROR: $*" >&2; exit 1; }
step() { echo; echo "== $*"; }

# ---------------------------------------------------------------- prerequisites
step "Checking Docker"
command -v docker >/dev/null || fail "docker is not installed (IT installs Docker Engine from the offline packages)."
docker info >/dev/null 2>&1 || fail "cannot talk to Docker: is the service running, and are you root (sudo)?"
compose_version="$(docker compose version --short 2>/dev/null || true)"
[ -n "$compose_version" ] || fail "the Docker Compose plugin is missing (docker compose version)."
major="${compose_version%%.*}"; rest="${compose_version#*.}"; minor="${rest%%.*}"
if [ "${major//[!0-9]/}" -lt 2 ] || { [ "${major//[!0-9]/}" -eq 2 ] && [ "${minor//[!0-9]/}" -lt 24 ]; }; then
  fail "Docker Compose $compose_version is too old: 2.24 or newer is needed."
fi
echo "Docker Compose $compose_version"

[ -f VERSION ] || fail "VERSION file missing: run this from the unpacked bundle folder."
VERSION="$(tr -d '[:space:]' < VERSION)"
echo "Bundle version $VERSION"

# ---------------------------------------------------------------- files
step "Checking the bundle files (SHA256SUMS)"
[ -f SHA256SUMS ] || fail "SHA256SUMS missing."
sha256sum --quiet -c --ignore-missing SHA256SUMS || fail "a file is damaged or changed: copy the bundle again."
echo "OK"

# ---------------------------------------------------------------- settings and certificate
step "Checking app.env and the certificate"
[ -f app.env ] || fail "app.env missing: cp app.env.example app.env && chmod 600 app.env, then fill every <...>."
if grep -nE '^[A-Z_]+=.*<[^>]*>' app.env >/dev/null; then
  grep -nE '^[A-Z_]+=.*<[^>]*>' app.env | cut -d= -f1 | sed 's/^/  still a placeholder: /' >&2
  fail "fill these values in app.env first."
fi
grep -qE '^APP_PROFILE=oracle\s*$' app.env || fail "app.env must say APP_PROFILE=oracle (demo data never runs on the VM)."
chmod 600 app.env
if [ -f ldap.env ]; then
  chmod 600 ldap.env
  if grep -nE '^[A-Z_]+=.*<[^>]*>' ldap.env >/dev/null && grep -qE '^AUTH_MODE=ldap' ldap.env; then
    fail "ldap.env switches to AUTH_MODE=ldap but still has <...> placeholders."
  fi
fi
[ -f nginx/certs/server.crt ] && [ -f nginx/certs/server.key ] \
  || fail "put IT's certificate in nginx/certs/server.crt and its key in nginx/certs/server.key (see nginx/certs/README.md)."
chmod 600 nginx/certs/server.key
if command -v openssl >/dev/null; then
  a="$(openssl x509 -in nginx/certs/server.crt -noout -pubkey 2>/dev/null | sha256sum)"
  b="$(openssl pkey -in nginx/certs/server.key -pubout 2>/dev/null | sha256sum)"
  [ "$a" = "$b" ] || fail "nginx/certs/server.key does not belong to nginx/certs/server.crt (or one is not PEM)."
  openssl x509 -in nginx/certs/server.crt -noout -checkend 2592000 >/dev/null \
    || echo "WARNING: the certificate expires within 30 days (or has expired)."
fi
echo "OK"

# ---------------------------------------------------------------- data folder (written by the app's user only)
mkdir -p data ldap
chown "$APP_UID:$APP_UID" data
chmod 750 data

# ---------------------------------------------------------------- images
step "Loading the images (offline)"
for tarfile in images/*.tar; do
  [ -e "$tarfile" ] || fail "no image files in images/."
  if ! grep -q " images/$(basename "$tarfile")\$" SHA256SUMS; then
    echo "Removing $tarfile (from an older bundle)"; rm -f "$tarfile"; continue
  fi
  echo "docker load < $tarfile"
  docker load -i "$tarfile" | sed 's/^/  /'
done
docker image inspect "cpc:$VERSION" >/dev/null 2>&1 || fail "image cpc:$VERSION is not loaded."
docker image inspect nginx:1.27.3-alpine >/dev/null 2>&1 || fail "image nginx:1.27.3-alpine is not loaded."

# ---------------------------------------------------------------- .env: the version to run (ports kept)
step "Setting APP_VERSION=$VERSION"
previous=""
if [ -f .env ]; then
  previous="$(sed -n 's/^APP_VERSION=//p' .env | head -n1)"
  grep -vE '^(APP_VERSION=|# previous version: )' .env > .env.new || true
else
  printf '# Written by scripts/install.sh. HTTPS_PORT / HTTP_PORT may be added here (defaults 443 / 80).\n' > .env.new
fi
[ -n "$previous" ] && [ "$previous" != "$VERSION" ] && echo "# previous version: $previous" >> .env.new
echo "APP_VERSION=$VERSION" >> .env.new
mv .env.new .env
[ -n "$previous" ] && echo "Previous version: $previous (kept loaded for a rollback)"

# ---------------------------------------------------------------- start
step "Starting"
docker compose up -d --remove-orphans
bash ./scripts/app.sh wait

step "Done"
docker compose ps
cat <<EOF

Next:
  bash ./scripts/app.sh check                      # "Schema OK"
  bash ./scripts/app.sh flask create-user --username <name> --role SYS_ADMIN     (first install only)
  bash ./scripts/app.sh flask seed-reference --actor <name>                       (first install only)
Daily jobs (crontab -e as root), see README.md "Daily jobs".
EOF
