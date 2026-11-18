#!/usr/bin/env bash
#
# Give the desktop user access to ZSA keyboards over USB.
#
# Purpose:       install 50-zsa.rules into /etc/udev/rules.d, reload udev, and
#                re-run the rules on connected ZSA boards so the ACL applies
#                without replugging.
# Usage:         sudo ./install-zsa-udev.sh
# Preconditions: run as root, from any cwd; 50-zsa.rules must sit next to this
#                script. Idempotent — safe to re-run.

set -euo pipefail

src_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)

if [[ $EUID -ne 0 ]]; then
	echo "must run as root: sudo $0" >&2
	exit 1
fi

install -D -m 0644 "$src_dir/50-zsa.rules" /etc/udev/rules.d/50-zsa.rules
udevadm control --reload

for dev in /sys/bus/usb/devices/*; do
	case "$(cat "$dev/idVendor" 2>/dev/null)" in 3297 | feed | 16c0 | 0483) ;; *) continue ;; esac
	udevadm trigger --action=change --parent-match="$dev"
	udevadm settle
	getfacl -p "/dev/bus/usb/$(printf '%03d/%03d' "$(cat "$dev/busnum")" "$(cat "$dev/devnum")")"
	for h in "$dev"/*/*/hidraw/hidraw*; do
		[[ -e "$h" ]] && getfacl -p "/dev/$(basename "$h")"
	done
done
