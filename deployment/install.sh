#!/usr/bin/env bash
# Capability Portfolio Command: install, or update, on the offline VM. Needs Docker Engine and, normally, the VM's own
# nginx. Nothing is downloaded: the application image is in images/.
#
#   tar -xzf cpc-<version>.tar.gz && cd cpc-<version>
#   sudo ./install.sh            first install, or an update with a newer kit (keeps the settings and the data)
#   sudo ./install.sh --yes      no questions: the defaults, or the CPC_* values below
#
# In order: checks the VM and this kit; loads the image; installs into /opt/cpc; on a first install writes app.env
# (the database: built-in or Oracle; a new SETTINGS_KEY); the HTTPS certificate (IT's, from certs/, or a self-signed
# one); starts the app container (on 127.0.0.1 only) and waits until it is healthy; adds the site to the VM's nginx
# (checked with nginx -t before the reload; without nginx on the VM the bundled nginx container is used); on a first
# install creates the first system administrator; installs the daily jobs.
#
# Values (environment) for --yes or to change a default:
#   CPC_HOME            the install folder (/opt/cpc)
#   CPC_SERVER_NAME     the name users type in the browser (this VM's name)
#   CPC_HTTPS_PORT      the HTTPS port (443)
#   CPC_APP_PORT        the app's port on 127.0.0.1, for nginx (8770)
#   CPC_DB              builtin | oracle (first install; builtin)
#   CPC_ORACLE_DSN, CPC_ORACLE_USER, CPC_ORACLE_SCHEMA, CPC_ORACLE_PASSWORD   (CPC_DB=oracle)
#   CPC_NGINX           host | bundled | none (host when nginx is installed on the VM, else bundled)
#   CPC_ADMIN           the first system administrator's username, e.g. a U number (first install)
#   CPC_ADMIN_PASSWORD  their password, only with --yes (otherwise it is asked, hidden)
#   CPC_CRON            yes | no: install the daily jobs in /etc/cron.d (yes)
set -euo pipefail
# Never stop without saying where: a command that fails unexpectedly names itself and its line.
trap 'echo "ERROR: install.sh stopped at line $LINENO: $BASH_COMMAND" >&2' ERR

KIT="$(cd "$(dirname "$0")" && pwd)"
CPC_HOME="${CPC_HOME:-/opt/cpc}"
APP_UID=10001
CONTAINER=cpc-app
PROXY=cpc-proxy
NETWORK=cpc-net
NGINX_IMAGE=nginx:1.27.3-alpine
YES=0

usage() { sed -n '2,25p' "$0" | sed 's/^# \{0,1\}//'; exit "${1:-0}"; }
fail() { echo "ERROR: $*" >&2; exit 1; }
step() { echo; echo "== $*"; }
warn() { echo "WARNING: $*" >&2; }

for arg in "$@"; do
  case "$arg" in
    --yes|-y) YES=1 ;;
    --help|-h) usage 0 ;;
    *) echo "Unknown option: $arg" >&2; usage 2 ;;
  esac
done

interactive() { [ "$YES" -eq 0 ] && [ -t 0 ]; }

# ask "question" "default": the answer (the default when there are no questions). The prompt goes to the terminal.
ask() {
  local answer=""
  if interactive; then
    read -r -p "$1 [$2]: " answer
  fi
  echo "${answer:-$2}"
}

ask_secret() {
  local answer=""
  if interactive; then
    read -r -s -p "$1: " answer
    echo >&2
  fi
  echo "$answer"
}

is_ip() { [[ "$1" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; }

# The VM's first IPv4 address, or nothing (hostname -I is not on every distribution; never a reason to stop).
vm_ip() {
  local ip=""
  ip="$(hostname -I 2>/dev/null | awk '{print $1}' || true)"
  if [ -z "$ip" ] && command -v ip >/dev/null 2>&1; then
    ip="$(ip -4 -o addr show scope global 2>/dev/null | awk '{print $4}' | cut -d/ -f1 | head -n1 || true)"
  fi
  echo "$ip"
}

# ---------------------------------------------------------------- 1. the VM and the kit
step "1. Checking the VM and this kit"
[ "$(id -u)" -eq 0 ] || fail "run it as root: sudo ./install.sh"
command -v docker >/dev/null || fail "Docker is not installed (IT installs Docker Engine from the offline packages)."
docker info >/dev/null 2>&1 || fail "Docker is not running: systemctl enable --now docker"
for tool in sha256sum tar openssl; do
  command -v "$tool" >/dev/null || fail "$tool is missing on the VM."
done
[ -f "$KIT/VERSION" ] || fail "VERSION is missing: run install.sh from the unpacked kit folder."
VERSION="$(tr -d '[:space:]' < "$KIT/VERSION")"
[ -f "$KIT/SHA256SUMS" ] || fail "SHA256SUMS is missing: copy the kit again."
if [ "$KIT" = "$CPC_HOME" ]; then
  # Run again from the install folder (e.g. after a new certificate): the images stayed in the kit, already loaded.
  (cd "$KIT" && sha256sum --quiet -c --ignore-missing SHA256SUMS) || fail "a file in $CPC_HOME was changed: run install.sh from the kit."
else
  (cd "$KIT" && sha256sum --quiet -c SHA256SUMS) || fail "a file of the kit is damaged or changed: copy it again."
fi
PLATFORM="$(tr -d '[:space:]' < "$KIT/IMAGE_PLATFORM" 2>/dev/null || echo linux/amd64)"
case "$(uname -m)" in
  x86_64|amd64) MACHINE=linux/amd64 ;;
  aarch64|arm64) MACHINE=linux/arm64 ;;
  *) MACHINE="linux/$(uname -m)" ;;
esac
[ "$PLATFORM" = "$MACHINE" ] || fail "this kit is for $PLATFORM, the VM is $MACHINE: build the kit with -Platform $MACHINE."
echo "Kit $VERSION ($PLATFORM), Docker $(docker version --format '{{.Server.Version}}' 2>/dev/null || echo '?')"

# ---------------------------------------------------------------- 2. the image (offline)
step "2. Loading the application image"
if docker image inspect "cpc:$VERSION" >/dev/null 2>&1; then
  echo "cpc:$VERSION is already loaded"
else
  [ -f "$KIT/images/cpc-$VERSION.tar" ] || fail "images/cpc-$VERSION.tar is missing."
  docker load -i "$KIT/images/cpc-$VERSION.tar" | sed 's/^/  /'
fi
docker image inspect "cpc:$VERSION" >/dev/null 2>&1 || fail "the image cpc:$VERSION did not load."

# ---------------------------------------------------------------- 3. the install folder
step "3. Installing into $CPC_HOME"
mkdir -p "$CPC_HOME"/{data,certs,ldap,backups,nginx,scripts}
FIRST=0
[ -f "$CPC_HOME/app.env" ] || FIRST=1
PREVIOUS=""
if [ -f "$CPC_HOME/install.conf" ]; then
  # The answers of the last install are this run's defaults.
  # shellcheck disable=SC1091
  . "$CPC_HOME/install.conf"
  PREVIOUS="${INSTALLED_VERSION:-}"
fi
if [ "$KIT" != "$CPC_HOME" ]; then
  for item in install.sh VERSION IMAGE_PLATFORM SHA256SUMS README.md README-AR.md app.env.example ldap.env.example \
              scripts nginx docs oracle-scripts; do
    [ -e "$KIT/$item" ] && cp -a "$KIT/$item" "$CPC_HOME/"
  done
  for readme in certs/README.md ldap/README.md; do
    [ -f "$KIT/$readme" ] && cp -a "$KIT/$readme" "$CPC_HOME/$readme"
  done
fi
chmod 755 "$CPC_HOME/install.sh" "$CPC_HOME"/scripts/*.sh
chown "$APP_UID:$APP_UID" "$CPC_HOME/data"
chmod 750 "$CPC_HOME/data"
chmod 700 "$CPC_HOME/backups" "$CPC_HOME/certs"
if [ "$FIRST" -eq 0 ] && [ -n "$PREVIOUS" ] && [ "$PREVIOUS" != "$VERSION" ]; then
  echo "Update $PREVIOUS -> $VERSION: a backup first"
  bash "$CPC_HOME/scripts/app.sh" backup || fail "the backup before the update failed: nothing was changed."
fi

# ---------------------------------------------------------------- 4. app.env (first install only)
SERVER_NAME="${CPC_SERVER_NAME:-${SERVER_NAME:-}}"
if [ -z "$SERVER_NAME" ]; then
  guess="$(hostname -f 2>/dev/null || hostname)"
  case "$guess" in localhost*|"") guess="$(vm_ip)" ;; esac
  SERVER_NAME="$(ask "The name users type in the browser (DNS name or IP address)" "$guess")"
fi
[[ "$SERVER_NAME" =~ ^[A-Za-z0-9.-]+$ ]] || fail "the server name may hold letters, digits, dots and hyphens only."
HTTPS_PORT="${CPC_HTTPS_PORT:-${HTTPS_PORT:-443}}"
APP_PORT="${CPC_APP_PORT:-${APP_PORT:-8770}}"
[[ "$HTTPS_PORT" =~ ^[0-9]+$ ]] && [[ "$APP_PORT" =~ ^[0-9]+$ ]] || fail "the ports must be numbers."

if [ "$FIRST" -eq 1 ]; then
  step "4. The settings (app.env)"
  DB="${CPC_DB:-}"
  if [ -z "$DB" ]; then
    echo "The database:"
    echo "  1 = built-in: a file in $CPC_HOME/data (start now; move to Oracle later from Settings > Database)"
    echo "  2 = Oracle: the DBA has run oracle-scripts/ on an EMPTY database (docs/oracle-migration.md)"
    case "$(ask "Choose" "1")" in 2|oracle) DB=oracle ;; *) DB=builtin ;; esac
  fi
  KEY="$(openssl rand -base64 32)"
  umask 077
  {
    echo "# Capability Portfolio Command - settings (written by install.sh on $(date +%F); see app.env.example)."
    echo "# Never copy its values into a ticket, chat or log. Changed? Run: $CPC_HOME/scripts/app.sh restart"
    echo "APP_ENV=production"
    echo "APP_TIMEZONE=Asia/Dubai"
    echo "LOG_LEVEL=INFO"
    echo "TRUSTED_PROXY_COUNT=1"
    echo "APP_THREADS=8"
    echo "AUTH_MODE=local"
    echo "SESSION_IDLE_MINUTES=30"
    echo "SESSION_ABSOLUTE_HOURS=12"
    echo "REPORTS_OUTPUT_DIR=/app/data/reports"
    echo "# The key that encrypts the passwords saved in Settings. Keep a copy with the backups (never in Git or a ticket)."
    echo "SETTINGS_KEY=$KEY"
    if [ "$DB" = oracle ]; then
      DSN="${CPC_ORACLE_DSN:-$(ask "Oracle address (host:port/service)" "")}"
      OUSER="${CPC_ORACLE_USER:-$(ask "Oracle runtime account" "CPC_APP")}"
      OSCHEMA="${CPC_ORACLE_SCHEMA:-$(ask "Oracle schema (owner of the tables)" "CPC_OWNER")}"
      OPASS="${CPC_ORACLE_PASSWORD:-$(ask_secret "Password of $OUSER")}"
      [ -n "$DSN" ] && [ -n "$OPASS" ] || { rm -f "$CPC_HOME/app.env.new"; fail "the Oracle address and password are needed."; }
      echo "# The database: Oracle (an empty schema: the app never runs on the demo data)."
      echo "APP_PROFILE=oracle"
      echo "ORACLE_DSN=$DSN"
      echo "ORACLE_USER=$OUSER"
      echo "ORACLE_PASSWORD=$OPASS"
      echo "ORACLE_SCHEMA=$OSCHEMA"
      echo "ORACLE_POOL_MAX=8"
      echo "ORACLE_TIMEOUT_SECONDS=10"
    else
      echo "# The database: built-in, one file in the data folder (the profile is called demo, but with APP_ENV=production"
      echo "# it starts empty: no demo records and no mock accounts). Moving to Oracle: Settings > Database (docs/SETTINGS.md)."
      echo "APP_PROFILE=demo"
      echo "DEMO_DB_PATH=/app/data/cpc.db"
    fi
  } > "$CPC_HOME/app.env.new"
  umask 022
  mv "$CPC_HOME/app.env.new" "$CPC_HOME/app.env"
  chmod 600 "$CPC_HOME/app.env"
  echo "Written $CPC_HOME/app.env (database: $DB)"
else
  step "4. The settings: keeping $CPC_HOME/app.env"
  grep -qE '^APP_ENV=production\s*$' "$CPC_HOME/app.env" || fail "$CPC_HOME/app.env must say APP_ENV=production."
fi
chmod 600 "$CPC_HOME/app.env"
[ -f "$CPC_HOME/ldap.env" ] && chmod 600 "$CPC_HOME/ldap.env"

# ---------------------------------------------------------------- 5. the certificate
step "5. The HTTPS certificate"
CERT="$CPC_HOME/certs/server.crt"
KEYFILE="$CPC_HOME/certs/server.key"
if [ -f "$KIT/certs/server.crt" ] && [ -f "$KIT/certs/server.key" ] && [ "$KIT" != "$CPC_HOME" ]; then
  cp "$KIT/certs/server.crt" "$CERT"
  cp "$KIT/certs/server.key" "$KEYFILE"
  echo "Using IT's certificate from the kit's certs/ folder"
elif [ -f "$CERT" ] && [ -f "$KEYFILE" ]; then
  echo "Keeping $CERT"
else
  VM_IP="$(vm_ip)"
  if is_ip "$SERVER_NAME"; then SAN="IP:$SERVER_NAME"; else SAN="DNS:$SERVER_NAME"; fi
  [ -n "$VM_IP" ] && [ "$VM_IP" != "$SERVER_NAME" ] && SAN="$SAN,IP:$VM_IP"
  openssl req -x509 -newkey rsa:3072 -sha256 -days 825 -nodes -keyout "$KEYFILE" -out "$CERT" \
    -subj "/CN=$SERVER_NAME" -addext "subjectAltName=$SAN" >/dev/null 2>&1 \
    || fail "openssl could not make a certificate (it needs OpenSSL 1.1.1 or newer)."
  touch "$CPC_HOME/certs/SELF-SIGNED"
  warn "no certificate from IT: a self-signed one was made for $SAN. Browsers warn about it until IT's certificate"
  warn "replaces it (put server.crt and server.key in $CPC_HOME/certs/, delete certs/SELF-SIGNED, run install.sh again)."
fi
a="$(openssl x509 -in "$CERT" -noout -pubkey 2>/dev/null | sha256sum || true)"
b="$(openssl pkey -in "$KEYFILE" -pubout 2>/dev/null | sha256sum || true)"
[ "$a" = "$b" ] || fail "$KEYFILE does not belong to $CERT (or one of them is not PEM)."
openssl x509 -in "$CERT" -noout -checkend 2592000 >/dev/null || warn "the certificate expires within 30 days (or has expired)."
chmod 600 "$KEYFILE"
chmod 644 "$CERT"

# ---------------------------------------------------------------- 6. the app container
step "6. Starting the app (cpc:$VERSION on 127.0.0.1:$APP_PORT)"
docker network inspect "$NETWORK" >/dev/null 2>&1 || docker network create "$NETWORK" >/dev/null
docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
env_files=(--env-file "$CPC_HOME/app.env")
[ -f "$CPC_HOME/ldap.env" ] && env_files+=(--env-file "$CPC_HOME/ldap.env")
docker run -d --name "$CONTAINER" --restart unless-stopped \
  --network "$NETWORK" --network-alias app \
  -p "127.0.0.1:$APP_PORT:8080" \
  "${env_files[@]}" -e APP_LISTEN=0.0.0.0:8080 \
  -v "$CPC_HOME/data:/app/data:Z" -v "$CPC_HOME/ldap:/app/ldap:ro,z" \
  --read-only --tmpfs /tmp:size=256m --cap-drop ALL --security-opt no-new-privileges:true \
  --log-driver json-file --log-opt max-size=20m --log-opt max-file=10 \
  --label "cpc.version=$VERSION" \
  "cpc:$VERSION" >/dev/null
bash "$CPC_HOME/scripts/app.sh" wait 180 || fail "the app did not start (its last lines are above)."

# ---------------------------------------------------------------- 7. nginx
NGINX="${CPC_NGINX:-${NGINX_MODE:-}}"
if [ -z "$NGINX" ]; then
  if command -v nginx >/dev/null 2>&1; then NGINX=host; else NGINX=bundled; fi
fi
PORT_SUFFIX=""
[ "$HTTPS_PORT" = 443 ] || PORT_SUFFIX=":$HTTPS_PORT"
case "$NGINX" in
  host)
    step "7. Adding the site to this VM's nginx"
    command -v nginx >/dev/null 2>&1 || fail "CPC_NGINX=host but nginx is not installed."
    docker rm -f "$PROXY" >/dev/null 2>&1 || true
    # The folder nginx's http block includes: http.d on Alpine (whose conf.d, if any, is included outside http), else
    # conf.d (RHEL, Debian, Ubuntu, SUSE, nginx.org packages). nginx -t below refuses a wrong one anyway.
    CONF_DIR="${CPC_NGINX_CONF_DIR:-}"
    if [ -z "$CONF_DIR" ]; then
      includes="$(nginx -T 2>/dev/null | grep -E '^[[:space:]]*include[[:space:]]' || true)"
      for dir in /etc/nginx/http.d /etc/nginx/conf.d; do
        if [ -d "$dir" ] && printf '%s\n' "$includes" | grep -qF "$dir/*.conf"; then CONF_DIR="$dir"; break; fi
      done
    fi
    [ -n "$CONF_DIR" ] && [ -d "$CONF_DIR" ] \
      || fail "cannot tell which folder nginx's http block includes: set CPC_NGINX_CONF_DIR=/that/folder and run again."
    SITE="$CONF_DIR/cpc.conf"
    BACKUP=""
    # The previous site is kept outside nginx's folder (nothing there but sites), to put back if nginx refuses the new one.
    if [ -f "$SITE" ]; then BACKUP="$CPC_HOME/backups/nginx-cpc.conf.$(date +%Y%m%d%H%M%S)"; cp -a "$SITE" "$BACKUP"; fi
    sed -e "s|@SERVER_NAME@|$SERVER_NAME|g" -e "s|@HTTPS_PORT@|$HTTPS_PORT|g" -e "s|@APP_PORT@|$APP_PORT|g" \
        -e "s|@PORT_SUFFIX@|$PORT_SUFFIX|g" -e "s|@CERT@|$CERT|g" -e "s|@KEY@|$KEYFILE|g" -e "s|@HOME@|$CPC_HOME|g" \
        "$CPC_HOME/nginx/cpc-site.conf.template" > "$SITE"
    if command -v getenforce >/dev/null 2>&1 && [ "$(getenforce 2>/dev/null)" = Enforcing ]; then
      # SELinux: nginx may only pass requests to the app when allowed to open network connections.
      setsebool -P httpd_can_network_connect 1 || warn "setsebool httpd_can_network_connect failed: nginx may answer 502."
      if [ "$HTTPS_PORT" != 443 ] && command -v semanage >/dev/null 2>&1; then
        semanage port -a -t http_port_t -p tcp "$HTTPS_PORT" 2>/dev/null || semanage port -m -t http_port_t -p tcp "$HTTPS_PORT" || true
      fi
    fi
    if ! nginx -t >/dev/null 2>&1; then
      nginx -t || true
      if [ -n "$BACKUP" ]; then mv -f "$BACKUP" "$SITE"; else rm -f "$SITE"; fi
      fail "nginx refused the new site (its message is above); nginx was left as it was."
    fi
    # Our site has two server_name lines (port 80 and HTTPS); more means another site answers to the same name.
    same="$(nginx -T 2>/dev/null | grep -cF "server_name $SERVER_NAME;" || true)"
    [ "${same:-0}" -gt 2 ] && warn "another nginx site also answers to $SERVER_NAME: make sure $SITE is the one used."
    # Reload a running nginx (systemd, or its pid file without systemd); start it when it is not running.
    if command -v systemctl >/dev/null 2>&1 && systemctl is-active --quiet nginx; then
      systemctl reload nginx
    elif nginx -s reload >/dev/null 2>&1; then
      :
    elif command -v systemctl >/dev/null 2>&1 && systemctl enable --now nginx >/dev/null 2>&1; then
      :
    else
      nginx || fail "nginx did not start (its message is above)."
    fi
    echo "Site: $SITE"
    ;;
  bundled)
    step "7. Starting the bundled nginx (no nginx on this VM)"
    if ! docker image inspect "$NGINX_IMAGE" >/dev/null 2>&1; then
      [ -f "$KIT/images/nginx-1.27.3-alpine.tar" ] || fail "images/nginx-1.27.3-alpine.tar is missing."
      docker load -i "$KIT/images/nginx-1.27.3-alpine.tar" | sed 's/^/  /'
    fi
    docker rm -f "$PROXY" >/dev/null 2>&1 || true
    docker run -d --name "$PROXY" --restart unless-stopped --network "$NETWORK" \
      -p "$HTTPS_PORT:443" -p 80:80 \
      -v "$CPC_HOME/nginx/nginx.conf:/etc/nginx/nginx.conf:ro,z" -v "$CPC_HOME/certs:/etc/nginx/certs:ro,z" \
      --security-opt no-new-privileges:true --log-driver json-file --log-opt max-size=20m --log-opt max-file=10 \
      "$NGINX_IMAGE" >/dev/null
    sleep 2
    [ "$(docker inspect -f '{{.State.Running}}' "$PROXY" 2>/dev/null)" = true ] \
      || { docker logs --tail 30 "$PROXY" >&2 || true; fail "the nginx container did not start (ports $HTTPS_PORT or 80 in use?)."; }
    ;;
  none)
    step "7. No web server (CPC_NGINX=none): the app answers on http://127.0.0.1:$APP_PORT on this VM only"
    docker rm -f "$PROXY" >/dev/null 2>&1 || true
    ;;
  *) fail "CPC_NGINX must be host, bundled or none." ;;
esac

# Through nginx, the way a browser comes: nginx -t cannot see a port taken by another program.
if [ "$NGINX" != none ] && command -v curl >/dev/null 2>&1; then
  ok=0
  for _ in 1 2 3 4 5; do
    if curl -sk --max-time 5 --resolve "$SERVER_NAME:$HTTPS_PORT:127.0.0.1" \
         "https://$SERVER_NAME:$HTTPS_PORT/api/v1/health" | grep -q '"UP"'; then ok=1; break; fi
    sleep 2
  done
  if [ "$ok" -eq 1 ]; then
    echo "Checked: https://$SERVER_NAME$PORT_SUFFIX/ answers through nginx"
  else
    warn "https://$SERVER_NAME$PORT_SUFFIX/ does not answer through nginx yet: check 'nginx -t', 'journalctl -u nginx'"
    warn "and that port $HTTPS_PORT is free for nginx (ss -ltnp | grep :$HTTPS_PORT)."
  fi
fi

# ---------------------------------------------------------------- the answers, for the next update
{
  echo "# Written by install.sh: the answers of the last install (the defaults of the next one). No secrets here."
  printf 'INSTALLED_VERSION=%q\nPREVIOUS_VERSION=%q\nSERVER_NAME=%q\nHTTPS_PORT=%q\nAPP_PORT=%q\nNGINX_MODE=%q\n' \
    "$VERSION" "$PREVIOUS" "$SERVER_NAME" "$HTTPS_PORT" "$APP_PORT" "$NGINX"
} > "$CPC_HOME/install.conf"
chmod 644 "$CPC_HOME/install.conf"

# The VM's firewall must let users reach the HTTPS port (IT's decision: only a hint here).
if [ "$NGINX" != none ]; then
  if command -v firewall-cmd >/dev/null 2>&1 && firewall-cmd --state >/dev/null 2>&1; then
    if ! firewall-cmd --list-ports 2>/dev/null | grep -qw "$HTTPS_PORT/tcp" \
       && ! { [ "$HTTPS_PORT" = 443 ] && firewall-cmd --list-services 2>/dev/null | grep -qw https; }; then
      warn "the firewall may block port $HTTPS_PORT: firewall-cmd --permanent --add-port=$HTTPS_PORT/tcp && firewall-cmd --reload"
    fi
  elif command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q "Status: active"; then
    ufw status 2>/dev/null | grep -qE "^$HTTPS_PORT(/tcp)?[[:space:]]+ALLOW" \
      || warn "the firewall may block port $HTTPS_PORT: ufw allow $HTTPS_PORT/tcp"
  fi
fi

# ---------------------------------------------------------------- 8. the first administrator
if [ "$FIRST" -eq 1 ]; then
  step "8. The first system administrator"
  ADMIN="${CPC_ADMIN:-$(ask "Username of the first system administrator (e.g. your U number)" "admin")}"
  if [ "$YES" -eq 1 ] && [ -n "${CPC_ADMIN_PASSWORD:-}" ]; then
    printf '%s\n' "$CPC_ADMIN_PASSWORD" | docker exec -i "$CONTAINER" flask --app wsgi setup-database --admin "$ADMIN" \
      --password-stdin || fail "the administrator was not created (the message is above)."
  elif interactive; then
    echo "Choose their password (at least 8 characters; asked twice, not shown):"
    docker exec -it "$CONTAINER" flask --app wsgi setup-database --admin "$ADMIN" \
      || fail "the administrator was not created (the message is above); run: $CPC_HOME/scripts/app.sh flask setup-database --admin $ADMIN"
  else
    warn "no administrator yet: run $CPC_HOME/scripts/app.sh flask setup-database --admin <username>"
    ADMIN=""
  fi
fi

# ---------------------------------------------------------------- 9. the daily jobs
if [ "${CPC_CRON:-yes}" = yes ] && [ -d /etc/cron.d ]; then
  cat > /etc/cron.d/cpc <<EOF
# Capability Portfolio Command daily jobs (written by $CPC_HOME/install.sh).
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
15 1 * * * root $CPC_HOME/scripts/app.sh flask take-snapshot >> /var/log/cpc-jobs.log 2>&1
30 1 * * * root $CPC_HOME/scripts/app.sh flask run-schedules >> /var/log/cpc-jobs.log 2>&1
45 1 * * * root $CPC_HOME/scripts/app.sh flask purge-sessions >> /var/log/cpc-jobs.log 2>&1
0 2 * * * root $CPC_HOME/scripts/app.sh backup >> /var/log/cpc-jobs.log 2>&1
EOF
  chmod 644 /etc/cron.d/cpc
  DAILY="installed in /etc/cron.d/cpc"
else
  DAILY="not installed (no /etc/cron.d): see README.md, Daily jobs"
fi

# ---------------------------------------------------------------- done
step "Done: Capability Portfolio Command $VERSION"
case "$NGINX" in
  none) URL="http://127.0.0.1:$APP_PORT" ;;
  *) URL="https://$SERVER_NAME$PORT_SUFFIX/" ;;
esac
echo "Open:          $URL"
[ "$FIRST" -eq 1 ] && [ -n "${ADMIN:-}" ] && echo "Sign in as:    $ADMIN (the password you chose)"
echo "Settings:      $CPC_HOME/app.env    Data: $CPC_HOME/data    Backups: $CPC_HOME/backups"
echo "Daily jobs:    $DAILY"
[ -f "$CPC_HOME/certs/SELF-SIGNED" ] && echo "Certificate:   self-signed (browsers warn): replace it with IT's, see $CPC_HOME/certs/README.md"
echo "Everyday:      $CPC_HOME/scripts/app.sh status | logs | restart | backup | check"
