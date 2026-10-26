#!/usr/bin/env bash
# Debounced worker invoked after manual pacman/yay transactions on server hosts.

set -euo pipefail

source_dir=$(chezmoi source-path)
state_dir="${XDG_STATE_HOME:-$HOME/.local/state}/chezmoi-package-sync"
log_file="$state_dir/capture.log"
pending_file="$state_dir/pending"
git_lock="${TMPDIR:-/tmp}/chezmoi-git-$(id -u).lock"
reconcile_marker="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/chezmoi-package-reconcile.active"
mkdir -p "$state_dir"

log() { printf '%s  %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >>"$log_file"; }

[[ $(chezmoi data | jq -r '.profile | ascii_downcase') == server ]] || exit 0
[[ -e $reconcile_marker ]] && { log 'skipped: package reconciliation is active'; exit 0; }

if [[ ${1:-} == --schedule ]]; then
  : >"$pending_file"
  systemctl --user start --no-block chezmoi-package-capture.service
  exit 0
fi

# The timer is retry-only. A pull that changes package declarations must not be
# mistaken for local intent before this host has converged to those declarations.
[[ -e $pending_file ]] || exit 0

exec 9>"$git_lock"
flock -n 9 || { log 'deferred: another chezmoi git operation holds the lock'; exit 0; }

# Collapse a burst of pacman transactions from yay or Ansible into one snapshot.
sleep 3
[[ -e $reconcile_marker ]] && { log 'skipped: package reconciliation is active'; exit 0; }

if [[ -n $(git -C "$source_dir" status --porcelain) ]]; then
  log 'deferred: chezmoi source has uncommitted changes'
  exit 0
fi

if ! git -C "$source_dir" pull --rebase --quiet; then
  git -C "$source_dir" rebase --abort >/dev/null 2>&1 || true
  log 'failed: could not rebase onto origin'
  exit 1
fi

"$source_dir/scripts/update_server_package_lists.sh" >/dev/null

if ! git -C "$source_dir" diff --quiet -- packages/server/pacman.txt packages/server/aur.txt; then
  git -C "$source_dir" add packages/server/pacman.txt packages/server/aur.txt
  git -C "$source_dir" commit -q -m "Sync server packages from $(hostname -s)"
fi

if git -C "$source_dir" push -q; then
  rm -f -- "$pending_file"
  log "ok: published $(git -C "$source_dir" rev-parse --short HEAD)"
else
  log 'pending: package commit is local; push will retry on the next run'
  exit 1
fi
