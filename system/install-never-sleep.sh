#!/usr/bin/env bash
#
# Make this host never sleep, suspend or hibernate.
#
# Purpose:       install 30-never-sleep.conf into /etc/systemd/logind.conf.d,
#                mask every sleep target, and reload logind (SIGHUP) so it
#                takes effect without ending the session.
# Usage:         sudo ./install-never-sleep.sh
# Preconditions: run as root, from any cwd; 30-never-sleep.conf must sit next
#                to this script. Idempotent — safe to re-run.

set -euo pipefail

src_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)

if [[ $EUID -ne 0 ]]; then
	echo "must run as root: sudo $0" >&2
	exit 1
fi

install -D -m 0644 "$src_dir/30-never-sleep.conf" /etc/systemd/logind.conf.d/30-never-sleep.conf
systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target suspend-then-hibernate.target
systemctl kill -s HUP systemd-logind
systemd-analyze cat-config systemd/logind.conf | grep -E '^(HandleLid|HandleSuspend|HandleHibernate|IdleAction)'
