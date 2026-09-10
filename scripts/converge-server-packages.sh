#!/usr/bin/env bash
# Root-owned timer worker. Pulls committed declarations as the login user and
# runs the package-only convergence boundary when their content changes.

set -euo pipefail

if (( EUID != 0 )) || [[ $# -ne 3 ]]; then
  printf 'usage: %s SOURCE_DIR USER UID\n' "${0##*/}" >&2
  exit 2
fi

source_dir=$1
login_user=$2
login_uid=$3
state_dir=/var/lib/chezmoi-server-package-sync
applied_file="$state_dir/applied.sha256"
runtime_dir="/run/user/$login_uid"
reconcile_marker="$runtime_dir/chezmoi-package-reconcile.active"
ansible_tmp="$state_dir/ansible"
git_lock="/tmp/chezmoi-git-$login_uid.lock"

mkdir -p "$state_dir" "$ansible_tmp"
chmod 700 "$state_dir" "$ansible_tmp"
exec 9>/run/lock/chezmoi-server-package-converge.lock
flock -n 9 || exit 0
# The user's autoupdater owns this predictable lock in sticky /tmp. With
# fs.protected_regular enabled, root cannot reopen that user-owned file for
# writing even though it is root. flock only needs an open descriptor, so have
# the user create it when absent and let root open it read-only.
if [[ ! -e $git_lock ]]; then
  runuser -u "$login_user" -- touch "$git_lock"
fi
exec 8<"$git_lock"
flock -n 8 || exit 0

if [[ -n $(git -C "$source_dir" status --porcelain) ]]; then
  printf 'Skipping package convergence: chezmoi source is dirty\n' >&2
  exit 0
fi

runuser -u "$login_user" -- git -C "$source_dir" pull --ff-only --quiet

desired_hash=$(
  sha256sum \
    "$source_dir/packages/server/pacman.txt" \
    "$source_dir/packages/server/aur.txt" \
    "$source_dir/playbook.yml" \
    "$source_dir/scripts/reconcile-server-package-set.sh" |
    sha256sum | cut -d' ' -f1
)

if [[ -r $applied_file ]] && [[ $(<"$applied_file") == "$desired_hash" ]]; then
  exit 0
fi

mkdir -p "$runtime_dir"
: >"$reconcile_marker"
trap 'rm -f -- "$reconcile_marker"' EXIT

ANSIBLE_CONFIG="$source_dir/ansible.cfg" ANSIBLE_LOCAL_TEMP="$ansible_tmp" \
  ansible-playbook -i 'localhost,' -c local \
    --extra-vars "chezmoi_source_dir=$source_dir non_root_user=$login_user profile=server work=false" \
    "$source_dir/playbook.yml"

tmp_applied="$state_dir/applied.sha256.new"
printf '%s\n' "$desired_hash" >"$tmp_applied"
mv -f "$tmp_applied" "$applied_file"
