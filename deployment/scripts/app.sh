#!/usr/bin/env bash
# Everyday commands for Capability Portfolio Command on the VM (as root; the install folder is /opt/cpc):
#   /opt/cpc/scripts/app.sh status | start | stop | restart | logs [proxy] | check | version | url
#   /opt/cpc/scripts/app.sh flask <command> [options]   e.g. flask setup-database --admin U12345 (first administrator)
#   /opt/cpc/scripts/app.sh backup                      the database (built-in), files, reports and settings -> backups/
#   /opt/cpc/scripts/app.sh new-key                     a new SETTINGS_KEY
#   /opt/cpc/scripts/app.sh wait [seconds]              wait until the app is healthy (install.sh uses it)
# After changing app.env or ldap.env: restart. A new version: run install.sh from the new kit.
set -euo pipefail
trap 'echo "ERROR: app.sh stopped at line $LINENO: $BASH_COMMAND" >&2' ERR

cd "$(dirname "$0")/.."
HOME_DIR="$(pwd)"
CONTAINER=cpc-app
PROXY=cpc-proxy
KEEP_BACKUPS_DAYS="${CPC_KEEP_BACKUPS_DAYS:-14}"

usage() { sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'; exit 2; }
setting() { sed -n "s/^$1=//p" "$HOME_DIR/install.conf" 2>/dev/null | head -n1 | tr -d "'\"" || true; }
running() { [ "$(docker inspect -f '{{.State.Running}}' "$1" 2>/dev/null || echo false)" = true ]; }
exists() { docker inspect "$1" >/dev/null 2>&1; }

wait_healthy() {
  local limit=${1:-120} waited=0 state
  echo -n "Waiting for the app to be healthy"
  while [ "$waited" -lt "$limit" ]; do
    state="$(docker inspect -f '{{.State.Health.Status}}' "$CONTAINER" 2>/dev/null || true)"
    if [ "$state" = healthy ]; then echo " - healthy"; return 0; fi
    if [ "$(docker inspect -f '{{.State.Status}}' "$CONTAINER" 2>/dev/null || true)" = exited ]; then break; fi
    echo -n "."; sleep 3; waited=$((waited + 3))
  done
  echo
  echo "The app is not healthy. Its last lines:" >&2
  docker logs --tail 40 "$CONTAINER" >&2 || true
  return 1
}

url() {
  local name port mode
  name="$(setting SERVER_NAME)"; port="$(setting HTTPS_PORT)"; mode="$(setting NGINX_MODE)"
  if [ "$mode" = none ]; then echo "http://127.0.0.1:$(setting APP_PORT)"
  elif [ "${port:-443}" = 443 ]; then echo "https://$name/"
  else echo "https://$name:$port/"; fi
}

backup() {
  mkdir -p backups && chmod 700 backups
  local stamp out db_copy=""
  stamp="$(date +%Y%m%d-%H%M%S)"
  out="backups/cpc-$stamp.tar.gz"
  if grep -qE '^APP_PROFILE=demo' app.env 2>/dev/null && running "$CONTAINER"; then
    # The built-in database: a consistent copy made by the running app (SQLite online backup), not the live file.
    db_copy="data/backup-$stamp.db"
    docker exec -i "$CONTAINER" python - "/app/$db_copy" <<'PY'
import os, sqlite3, sys
src = sqlite3.connect(os.environ.get("DEMO_DB_PATH", "/app/data/cpc.db"))
dst = sqlite3.connect(sys.argv[1])
try:
    src.backup(dst)
finally:
    dst.close()
    src.close()
PY
  fi
  local items=(app.env install.conf certs) stopped_db=""
  if [ -z "$db_copy" ] && grep -qE '^APP_PROFILE=demo' app.env 2>/dev/null && ! running "$CONTAINER"; then
    stopped_db="data/cpc.db"  # the app is stopped: the file itself is consistent
  fi
  for f in ldap.env ldap data/files data/reports data/settings.key "$db_copy" "$stopped_db" "${stopped_db:+data/cpc.db-wal}"; do
    [ -n "$f" ] && [ -e "$f" ] && items+=("$f")
  done
  tar -czf "$out" "${items[@]}"
  chmod 600 "$out"
  [ -n "$db_copy" ] && rm -f "$db_copy"
  find backups -maxdepth 1 -name 'cpc-*.tar.gz' -mtime "+$KEEP_BACKUPS_DAYS" -delete 2>/dev/null || true
  if grep -qE '^APP_PROFILE=oracle' app.env 2>/dev/null; then
    echo "Written $out: files, reports and settings. The records are in Oracle: the DBA backs them up."
  else
    echo "Written $out: the database, files, reports and settings (kept $KEEP_BACKUPS_DAYS days)."
  fi
}

cmd="${1:-}"; [ $# -gt 0 ] && shift
case "$cmd" in
  status)
    for c in "$CONTAINER" "$PROXY"; do
      exists "$c" && docker ps -a --filter "name=^${c}$" --format "{{.Names}}  {{.Image}}  {{.Status}}"
    done
    echo "Version: $(setting INSTALLED_VERSION)   Address: $(url)" ;;
  start)   docker start "$CONTAINER" >/dev/null && wait_healthy && { exists "$PROXY" && docker start "$PROXY" >/dev/null || true; } ;;
  stop)    { exists "$PROXY" && docker stop "$PROXY" >/dev/null || true; }; docker stop "$CONTAINER" >/dev/null; echo "Stopped." ;;
  restart) docker restart "$CONTAINER" >/dev/null && wait_healthy && { exists "$PROXY" && docker restart "$PROXY" >/dev/null || true; } ;;
  logs)
    if [ "${1:-}" = proxy ]; then docker logs --tail 200 -f "$PROXY"; else docker logs --tail 200 -f "$CONTAINER"; fi ;;
  wait)    wait_healthy "$@" ;;
  check)   docker exec "$CONTAINER" flask --app wsgi check-schema ;;
  new-key) openssl rand -base64 32 ;;
  version) setting INSTALLED_VERSION ;;
  url)     url ;;
  flask)
    [ $# -gt 0 ] || { echo "usage: app.sh flask <command> [options]"; exit 2; }
    # A terminal gets a TTY (password prompts); cron does not.
    if [ -t 0 ]; then docker exec -it "$CONTAINER" flask --app wsgi "$@"
    else docker exec -i "$CONTAINER" flask --app wsgi "$@"; fi ;;
  backup)  backup ;;
  *) usage ;;
esac
