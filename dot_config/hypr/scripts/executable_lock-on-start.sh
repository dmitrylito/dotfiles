#!/bin/bash
# Locks the session as soon as it starts, so SDDM autologin never leaves an open
# desktop once the disk unlocks itself through the TPM. The Omarchy shell draws the
# lock screen, so this waits for its IPC to answer before locking.
#
# Run by the hyprland.start autostart in ~/.config/hypr/autostart.lua.
# LOCK_ON_START_WAIT_SECS (default 60) bounds the wait; on timeout it logs to the
# journal under the lock-on-start tag and exits 1, leaving the session unlocked.

wait_secs=${LOCK_ON_START_WAIT_SECS:-60}

while ((SECONDS < wait_secs)); do
  if omarchy-shell shell ping >/dev/null 2>&1; then
    exec omarchy system lock
  fi
  sleep 0.2
done

logger -t lock-on-start "omarchy shell did not answer within ${wait_secs}s; session left unlocked"
exit 1
