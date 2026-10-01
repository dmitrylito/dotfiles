#!/bin/bash
# One-off local State Mileage (IFTA) report for given vehicles and dates:
# per vehicle, restart emulator -> import prod readings -> replay GPS miles -> rebuild rollups.
# One vehicle at a time: the local Bigtable emulator (cbtemulator) is in-memory and
# gets OOM-killed by parallel long imports (~10KB RAM per reading row).
#
# Usage:
#   run_pipeline.sh <vehicle_ids_csv> <first_day> <last_day> [backend_checkout]
#     first_day/last_day: inclusive YYYY-MM-DD in each vehicle's customer timezone
#     (looked up from the local DB).
# Example (Q3 2026):
#   run_pipeline.sh 3502,6508 2026-07-01 2026-09-30
#
# Env: SRC_INSTANCE (default fleetchaser-default-production), LOG_DIR (default
# /tmp/state-mileage-import), WARMUP_HOURS (default 4; replay starts this much early
# so the state machine has prior readings at the window start).
# Preconditions: the fleetchaser compose stack is up (db + bigtable containers), and
# gcloud application-default credentials can read the prod Bigtable instance.
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
VEHICLES="$1"
FIRST_DAY="$2"
LAST_DAY="$3"
CHECKOUT="${4:-$HOME/Projects/backend}"
SRC_INSTANCE="${SRC_INSTANCE:-fleetchaser-default-production}"
LOG_DIR="${LOG_DIR:-/tmp/state-mileage-import}"
WARMUP_HOURS="${WARMUP_HOURS:-4}"
mkdir -p "$LOG_DIR"

export COMPOSE_FILE="$CHECKOUT/docker/docker-compose.yml"
# Worktrees miss gitignored files the containers need.
[ -f "$CHECKOUT/docker/.env" ] || cp "$HOME/Projects/backend/docker/.env" "$CHECKOUT/docker/.env"
[ -f "$CHECKOUT/fc-staging-media.json" ] || cp "$HOME/Projects/backend/fc-staging-media.json" "$CHECKOUT/"

psql_value() {
  docker exec fleetchaser-db-1 psql -U fleetchaser -d fleetchaser -tAc "$1"
}

to_utc() {  # <YYYY-MM-DD> <tz> -> UTC "YYYY-MM-DD HH:MM:SS" of local midnight
  date -u -d "TZ=\"$2\" $1 00:00" '+%F %T'
}

IFS=',' read -ra IDS <<< "$VEHICLES"
for id in "${IDS[@]}"; do
  tz=$(psql_value "SELECT c.timezone FROM vehicle_vehicle v JOIN accounting_customer c ON c.id = v.customer_id WHERE v.id = $id")
  [ -n "$tz" ] || { echo "vehicle $id: not found or customer has no timezone" >&2; exit 1; }
  report_start=$(to_utc "$FIRST_DAY" "$tz")
  report_end=$(to_utc "$(date -d "$LAST_DAY +1 day" +%F)" "$tz")
  replay_lower=$(date -u -d "$report_start UTC -$WARMUP_HOURS hours" '+%F %T')
  echo "===== vehicle $id ($tz): report $report_start -> $report_end UTC ====="

  echo "restarting emulator (wipes ALL emulator data)"
  docker restart fleetchaser-bigtable-1 > /dev/null
  sleep 8

  echo "importing readings"
  docker compose run --rm --no-deps backend ./manage.py dev_sync_readings \
    --vehicles="$id" --start="$replay_lower" --end="$report_end" \
    --src-instance-id "$SRC_INSTANCE" \
    > "$LOG_DIR/sync_${id}.log" 2>&1
  synced=$(grep -oE 'Synced [0-9]+' "$LOG_DIR/sync_${id}.log" | tail -1 | grep -oE '[0-9]+' || echo 0)

  echo "replaying miles + rollups"
  docker compose run --rm --no-deps -T \
    -e REPLAY_VEHICLE_IDS="$id" -e REPLAY_LOWER="$replay_lower" \
    -e REPORT_START="$report_start" -e REPORT_END="$report_end" -e REPORT_TZ="$tz" \
    backend python manage.py shell -c "$(cat "$SKILL_DIR/reprocess_state_mileage.py")" \
    > "$LOG_DIR/replay_${id}.log" 2>&1 || { tail -20 "$LOG_DIR/replay_${id}.log"; exit 1; }

  replayed=$(grep -oE ': [0-9]+ readings$' "$LOG_DIR/replay_${id}.log" | grep -oE '[0-9]+')
  if [ "$replayed" -lt "$synced" ]; then
    echo "vehicle $id: replay saw $replayed readings but import synced >= $synced — emulator lost data, rerun" >&2
    exit 1
  fi
  grep -E "^\[$id\]" "$LOG_DIR/replay_${id}.log"
done

echo "PIPELINE COMPLETE"
