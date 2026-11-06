# Apply already-fetched dotfile updates synchronously, then let the helper own
# its detached and throttled network update.
if [[ -x "$HOME/.local/bin/chezmoi-autoupdate" ]]; then
  "$HOME/.local/bin/chezmoi-autoupdate" --local
  if [[ -n ${CHEZMOI_AUTOUPDATE_FORCE:-} ]]; then
    unset CHEZMOI_AUTOUPDATE_FORCE
    "$HOME/.local/bin/chezmoi-autoupdate" --force
  else
    "$HOME/.local/bin/chezmoi-autoupdate"
  fi
fi
