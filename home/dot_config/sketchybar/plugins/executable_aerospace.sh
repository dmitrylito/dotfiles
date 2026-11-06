#!/usr/bin/env bash
# Repaints all ten workspace pills in one sketchybar call. Invoked by the
# spaces_watcher item, not per-pill, so a workspace switch forks `aerospace`
# twice rather than twenty times.
# All ten stay visible: focused is a filled pill, occupied an outlined one,
# empty is a dimmed number with no background.

source "${CONFIG_DIR:-$HOME/.config/sketchybar}/colors.sh"

FOCUSED="${FOCUSED_WORKSPACE:-$(aerospace list-workspaces --focused)}"
OCCUPIED="$(aerospace list-workspaces --monitor all --empty no)"

args=()
for sid in 1 2 3 4 5 6 7 8 9 10; do
  if [ "$sid" = "$FOCUSED" ]; then
    args+=(--set space."$sid" background.drawing=on \
           background.color="$BLUE" background.border_color="$BLUE" \
           icon.color=0xff1e1e2e)
  elif printf '%s\n' "$OCCUPIED" | grep -qx "$sid"; then
    args+=(--set space."$sid" background.drawing=on \
           background.color=0x00000000 background.border_color="$SURFACE1" \
           icon.color="$TEXT")
  else
    args+=(--set space."$sid" background.drawing=off icon.color="$OVERLAY")
  fi
done

sketchybar "${args[@]}"
