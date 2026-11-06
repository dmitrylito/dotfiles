#!/usr/bin/env bash
# Re-tile a window that AeroSpace floats at launch.
#
# Usage: retile.sh <app-bundle-id>
# Called from an on-window-detected rule via exec-and-forget.
#
# The delay is the whole point: some windows (System Settings) do not report
# themselves as resizable until a moment after they appear, so AeroSpace floats
# them, and a 'layout tiling' inside the rule itself runs too early and is lost.
# Retrying for a few seconds catches the window once it settles.

set -u
app="${1:?usage: retile.sh <app-bundle-id>}"

for _ in 1 2 3 4 5; do
  sleep 0.7
  wid="$(aerospace list-windows --all --format '%{window-id}|%{app-bundle-id}' \
         | awk -F'|' -v a="$app" 'index($2, a) { gsub(/ /, "", $1); print $1 }' \
         | head -1)"
  [ -n "$wid" ] && aerospace layout --window-id "$wid" tiling >/dev/null 2>&1
done
