#!/usr/bin/env bash
# Package reconciliation entry point. Chezmoi's run_onchange hook invokes this
# after relevant declarations change; it can also be run directly for audits.

set -euo pipefail

source_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
profile="$(chezmoi data | jq -er '.profile | ascii_downcase')"
# NOT jq -e: it exits 1 when the output value is false, which under set -e
# aborted this script silently on every non-work machine.
work="$(chezmoi data | jq -r '.work // false')"

case "$profile" in
  omarchy|server|mac) ;;
  *) printf 'Unsupported chezmoi profile: %s\n' "$profile" >&2; exit 2 ;;
esac

command -v ansible-playbook >/dev/null 2>&1 || {
  printf 'ansible-playbook is required; install Ansible first.\n' >&2
  exit 1
}

ansible_cfg="$source_dir/ansible.cfg"
playbook="$source_dir/playbook.yml"
extra_vars="chezmoi_source_dir=$source_dir non_root_user=$(id -un) profile=$profile work=$work"
# Keep the user-created controller directory separate from the root timer's
# scratch space. A shared /tmp/ansible-$USER can be created root-owned first.
tmp_root="${XDG_CACHE_HOME:-$HOME/.cache}/chezmoi/ansible"
mkdir -p "$tmp_root"
chmod 700 "$tmp_root"

printf 'Reconciling packages: profile=%s work=%s\n' "$profile" "$work"

if [[ $profile == mac ]]; then
  ANSIBLE_CONFIG="$ansible_cfg" ANSIBLE_LOCAL_TEMP="$tmp_root" \
    ansible-playbook -i 'localhost,' -c local --extra-vars "$extra_vars" "$playbook" "$@"
else
  runtime_dir="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
  reconcile_marker="$runtime_dir/chezmoi-package-reconcile.active"
  mkdir -p "$runtime_dir"
  : >"$reconcile_marker"
  trap 'rm -f -- "$reconcile_marker"' EXIT
  sudo ANSIBLE_CONFIG="$ansible_cfg" ANSIBLE_LOCAL_TEMP="$tmp_root" \
    ansible-playbook -i 'localhost,' -c local --extra-vars "$extra_vars" "$playbook" "$@"
fi
