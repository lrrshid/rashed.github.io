#!/usr/bin/env bash
# Everyday commands for Capability Portfolio Command on the VM. Run from the install folder (e.g. /opt/cpc):
#   bash ./scripts/app.sh status | start | stop | restart | logs [app|proxy] | wait | check | version
#   bash ./scripts/app.sh flask <command> [options]     e.g. flask create-user --username U12345 --role SYS_ADMIN
#   bash ./scripts/app.sh backup                        the data folder and the settings, into backups/
set -euo pipefail

cd "$(dirname "$0")/.."

usage() { sed -n '2,5p' "$0" | sed 's/^# \{0,1\}//'; exit 2; }

wait_healthy() {
  local limit=${1:-120} waited=0 state
  echo -n "Waiting for the app to be healthy"
  while [ "$waited" -lt "$limit" ]; do
    state="$(docker inspect -f '{{.State.Health.Status}}' "$(docker compose ps -q app 2>/dev/null)" 2>/dev/null || true)"
    if [ "$state" = "healthy" ]; then echo " - healthy"; return 0; fi
    echo -n "."; sleep 3; waited=$((waited + 3))
  done
  echo
  echo "The app is not healthy after ${limit}s. Its last lines:" >&2
  docker compose logs --tail 40 app >&2 || true
  return 1
}

cmd="${1:-}"; [ $# -gt 0 ] && shift
case "$cmd" in
  status)  docker compose ps ;;
  start)   docker compose up -d && wait_healthy ;;
  stop)    docker compose down ;;
  restart) docker compose up -d --force-recreate && wait_healthy ;;
  logs)    docker compose logs --tail 200 -f "$@" ;;
  wait)    wait_healthy "$@" ;;
  check)   docker compose exec -T app flask --app wsgi check-schema ;;
  version) sed -n 's/^APP_VERSION=//p' .env ;;
  flask)
    [ $# -gt 0 ] || { echo "usage: app.sh flask <command> [options]"; exit 2; }
    # A terminal gets a TTY (password prompts); cron and scripts do not.
    if [ -t 0 ]; then docker compose exec app flask --app wsgi "$@"
    else docker compose exec -T app flask --app wsgi "$@"; fi ;;
  backup)
    mkdir -p backups && chmod 700 backups
    out="backups/cpc-files-$(date +%Y%m%d-%H%M%S).tar.gz"
    files=(data app.env .env)
    for f in ldap.env ldap nginx/certs; do [ -e "$f" ] && files+=("$f"); done
    tar -czf "$out" "${files[@]}"
    chmod 600 "$out"
    echo "Written $out: uploaded files, scheduled reports and the settings. The records themselves are in Oracle (DBA backup)."
    ;;
  *) usage ;;
esac
