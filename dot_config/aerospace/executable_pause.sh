#!/usr/bin/env bash
# Suspend AeroSpace — and with it focus-follows-mouse — for a few seconds.
#
# Usage: pause.sh [seconds]   (default 8)
# Called from a key binding via exec-and-forget.
#
# For transient overlay panels (the Quick Look preview Messages opens when you
# click an image): AeroSpace never manages those, so focus-follows-mouse focuses
# whatever tiled window the cursor crosses and raises that app over the preview.
# There is no per-app opt-out — focus-follows-mouse has only an `enabled` flag.
#
# The timer is the only way back: `enable off` deactivates every binding mode,
# so no keystroke can re-enable it. The lock keeps a second press from cutting
# the first pause short.

set -u
secs="${1:-8}"
lock="${TMPDIR:-/tmp}/aerospace-pause.lock"

if ! mkdir "$lock" 2>/dev/null; then
  exit 0
fi
trap 'rmdir "$lock" 2>/dev/null' EXIT

aerospace enable off
sleep "$secs"
aerospace enable on
