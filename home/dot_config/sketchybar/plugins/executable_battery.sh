#!/usr/bin/env bash

source "${CONFIG_DIR:-$HOME/.config/sketchybar}/colors.sh"

BATT="$(pmset -g batt)"
PERCENTAGE="$(printf '%s' "$BATT" | grep -Eo '[0-9]+%' | head -1 | tr -d '%')"
CHARGING="$(printf '%s' "$BATT" | grep 'AC Power')"

[ -z "$PERCENTAGE" ] && exit 0

case "$PERCENTAGE" in
  9[0-9]|100) ICON="󰁹"; COLOR="$GREEN" ;;
  [6-8][0-9]) ICON="󰂂"; COLOR="$GREEN" ;;
  [3-5][0-9]) ICON="󰁿"; COLOR="$YELLOW" ;;
  [1-2][0-9]) ICON="󰁺"; COLOR="$YELLOW" ;;
  *)          ICON="󰂃"; COLOR="$RED" ;;
esac

[ -n "$CHARGING" ] && { ICON="󰂄"; COLOR="$TEAL"; }

sketchybar --set "$NAME" icon="$ICON" icon.color="$COLOR" label="${PERCENTAGE}%"
