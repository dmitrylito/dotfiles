#!/usr/bin/env bash
#
# Give the desktop user access to the Topping DX5 II over USB.
#
# Purpose:       install 70-topping-dx5-ii.rules into /etc/udev/rules.d, reload
#                udev, and re-run the rules on a connected DX5 II so the ACL
#                applies without replugging.
# Usage:         sudo ./install-topping-udev.sh
# Preconditions: run as root, from any cwd; 70-topping-dx5-ii.rules must sit next
#                to this script. Idempotent — safe to re-run.

set -euo pipefail

src_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)

if [[ $EUID -ne 0 ]]; then
	echo "must run as root: sudo $0" >&2
	exit 1
fi

install -D -m 0644 "$src_dir/70-topping-dx5-ii.rules" /etc/udev/rules.d/70-topping-dx5-ii.rules
udevadm control --reload

for dev in /sys/bus/usb/devices/*; do
	[[ "$(cat "$dev/idVendor" 2>/dev/null)" == 152a && "$(cat "$dev/idProduct" 2>/dev/null)" == 8750 ]] || continue
	udevadm trigger --action=change --parent-match="$dev"
	udevadm settle
	getfacl -p "/dev/bus/usb/$(printf '%03d/%03d' "$(cat "$dev/busnum")" "$(cat "$dev/devnum")")"
	for h in "$dev"/*/*/hidraw/hidraw*; do
		[[ -e "$h" ]] && getfacl -p "/dev/$(basename "$h")"
	done
done
