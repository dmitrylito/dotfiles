#!/usr/bin/env bash
# Converge the server's explicit package intent without removing packages that
# are still hard dependencies of the declared set.

set -euo pipefail

mode=apply
if [[ ${1:-} == --check ]]; then
  mode=check
  shift
fi

if [[ $# -lt 2 || $# -gt 5 ]]; then
  printf 'usage: %s [--check] PACMAN_LIST AUR_LIST [EXCLUDED_PACMAN_LIST] [ADDED_PACMAN_LIST] [ADDED_AUR_LIST]\n' "${0##*/}" >&2
  exit 2
fi

pacman_list=$1
aur_list=$2
excluded_list=${3:-}
added_list=${4:-}
added_aur_list=${5:-}
desired_file=$(mktemp "${TMPDIR:-/tmp}/server-packages.XXXXXXXX")
trap 'rm -f -- "$desired_file"' EXIT

{
  sed -E '/^[[:space:]]*(#|$)/d' "$pacman_list"
  sed -E '/^[[:space:]]*(#|$)/d' "$aur_list"
  if [[ -n $added_list && -f $added_list ]]; then
    sed -E '/^[[:space:]]*(#|$)/d' "$added_list"
  fi
  if [[ -n $added_aur_list && -f $added_aur_list ]]; then
    sed -E '/^[[:space:]]*(#|$)/d' "$added_aur_list"
  fi
  # Provisioned separately by the playbook, but intentionally explicit.
  printf '%s\n' zfs-linux-lts zfs-utils
} | sort -u | comm -23 - <(
  if [[ -n $excluded_list && -f $excluded_list ]]; then
    sed -E '/^[[:space:]]*(#|$)/d' "$excluded_list"
  fi | sort -u
) >"$desired_file"

list_prunable() {
  comm -23 <(pacman -Qettq | sort -u) "$desired_file"
}

list_extra_explicit() {
  comm -23 <(pacman -Qeq | sort -u) "$desired_file"
}

list_desired_as_dependencies() {
  comm -23 \
    <(comm -12 <(pacman -Qq | sort -u) "$desired_file") \
    <(pacman -Qeq | sort -u)
}

if [[ $mode == check ]]; then
  prunable=$(list_prunable)
  extra=$(list_extra_explicit)
  desired_asdeps=$(list_desired_as_dependencies)
  [[ -n $prunable ]] && printf 'would remove explicit leaves:\n%s\n' "$prunable"
  [[ -n $extra ]] && printf 'current undeclared explicit packages (required entries are demoted after pruning):\n%s\n' "$extra"
  [[ -n $desired_asdeps ]] && printf 'would mark declared packages explicit:\n%s\n' "$desired_asdeps"
  [[ -z $prunable && -z $extra && -z $desired_asdeps ]] && printf 'server package set already canonical\n'
  exit 0
fi

# Protect every installed declared package from pacman -Rs recursion and make
# install-reason metadata identical across the two servers.
mapfile -t desired_asdeps < <(list_desired_as_dependencies)
if (( ${#desired_asdeps[@]} )); then
  pacman -D --asexplicit "${desired_asdeps[@]}"
fi

# Removing one obsolete leaf can expose another explicit package that was only
# required (or optionally required) by it. Recompute until the graph settles.
while mapfile -t prunable < <(list_prunable) && (( ${#prunable[@]} )); do
  printf 'Removing undeclared explicit packages: %s\n' "${prunable[*]}"
  pacman -Rns --noconfirm "${prunable[@]}"
done

# Anything undeclared that remains is a hard dependency of a retained package.
# Keep the package but canonicalize its reason so the inventory generator does
# not publish it as user intent on this host.
mapfile -t required_extras < <(list_extra_explicit)
if (( ${#required_extras[@]} )); then
  printf 'Marking retained dependencies non-explicit: %s\n' "${required_extras[*]}"
  pacman -D --asdeps "${required_extras[@]}"
fi
