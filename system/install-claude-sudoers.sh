#!/usr/bin/env bash
#
# Install 50-claude-diagnostics into /etc/sudoers.d.
#
# Purpose:       let non-interactive Claude Code sessions run a fixed set of
#                read-only root diagnostics without a password prompt.
# Usage:         sudo ./install-claude-sudoers.sh [--uninstall]
# Preconditions: run as root, from any cwd; 50-claude-diagnostics must sit
#                next to this script. Idempotent — safe to re-run.
#
# A malformed file in /etc/sudoers.d breaks sudo for every user, so the target
# is validated in place and removed again if the full tree fails to parse.

set -euo pipefail

src_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
src="$src_dir/50-claude-diagnostics"
dest=/etc/sudoers.d/50-claude-diagnostics

if [[ $EUID -ne 0 ]]; then
	echo "must run as root: sudo $0 $*" >&2
	exit 1
fi

if [[ ${1:-} == --uninstall ]]; then
	rm -f "$dest"
	visudo -c >/dev/null
	echo "removed $dest"
	exit 0
fi

[[ -f $src ]] || { echo "missing $src" >&2; exit 1; }

visudo -cf "$src" >/dev/null || { echo "refusing to install: $src does not parse" >&2; exit 1; }

# Faults anywhere in /etc/sudoers.d fail a whole-tree `visudo -c`, so compare
# against a baseline — otherwise an unrelated broken file rolls this one back.
tree_faults() { visudo -c 2>&1 | grep -v 'parsed OK$' | sort || true; }

# 0440 is the only mode sudo accepts; anything else means the file is being
# ignored at runtime, so tightening it is a repair, not a policy change.
while read -r bad; do
	[[ -n $bad ]] || continue
	echo "repairing pre-existing $bad (was $(stat -c %a "$bad"), sudo requires 0440)"
	chmod 0440 "$bad"
done < <(tree_faults | sed -n 's|^\(/etc/sudoers\.d/[^:]*\): bad permissions.*|\1|p')

baseline=$(tree_faults)
if [[ -n $baseline ]]; then
	echo "warning: /etc/sudoers.d already has faults this script will not touch:" >&2
	echo "$baseline" | sed 's/^/  /' >&2
fi

backup=""
if [[ -f $dest ]]; then
	backup=$(mktemp)
	cp -a "$dest" "$backup"
fi

install -o root -g root -m 0440 "$src" "$dest"

introduced=$(comm -13 <(printf '%s\n' "$baseline") <(tree_faults))
if [[ -n $introduced ]]; then
	if [[ -n $backup ]]; then
		cp -a "$backup" "$dest"
	else
		rm -f "$dest"
	fi
	echo "rolled back — this file introduced:" >&2
	echo "$introduced" | sed 's/^/  /' >&2
	exit 1
fi

[[ -n $backup ]] && rm -f "$backup"

echo "installed $dest"
echo
echo "dmitrylito may now run without a password:"
sudo -l -U dmitrylito | sed -n '/NOPASSWD/,$p'
