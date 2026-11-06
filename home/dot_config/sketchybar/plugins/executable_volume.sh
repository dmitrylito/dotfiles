#!/usr/bin/env bash
# The label is hidden by default and revealed for a moment on volume_change, so
# the bar stays quiet but still shows the number while you are turning the knob.

source "${CONFIG_DIR:-$HOME/.config/sketchybar}/colors.sh"

case "$SENDER" in
  volume_change) VOLUME="$INFO" ;;
  mouse.clicked) osascript -e 'set volume output muted not (output muted of (get volume settings))'; exit 0 ;;
  mouse.exited)  sketchybar --set "$NAME" label.drawing=off; exit 0 ;;
  *) VOLUME="$(osascript -e 'output volume of (get volume settings)')" ;;
esac

case "$VOLUME" in
  [6-9][0-9]|100) ICON="󰕾" ;;
  [3-5][0-9])     ICON="󰖀" ;;
  [1-9]|[1-2][0-9]) ICON="󰕿" ;;
  *)              ICON="󰖁" ;;
esac

sketchybar --set "$NAME" icon="$ICON" icon.color="$TEAL" label="${VOLUME}%"

if [ "$SENDER" = "volume_change" ]; then
  sketchybar --set "$NAME" label.drawing=on
  ( sleep 2; sketchybar --set "$NAME" label.drawing=off ) &
fi
