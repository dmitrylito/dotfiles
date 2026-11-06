#!/bin/sh
# Wire ~/.ssh/config to source the chezmoi-managed defaults in
# ~/.ssh/config.d/ (keepalive, agent/keychain, identity).
#
# ~/.ssh/config itself is intentionally NOT managed by chezmoi: it holds
# host-specific IPs/usernames that must stay off the public dotfiles repo.
# So this idempotent bootstrap adds only the `Include` line, leaving any
# existing host entries untouched. Runs on every profile (mac/omarchy/server).
set -eu

ssh_dir="$HOME/.ssh"
config="$ssh_dir/config"
include_line="Include ~/.ssh/config.d/*"

mkdir -p "$ssh_dir"
chmod 700 "$ssh_dir"

if [ ! -e "$config" ]; then
	touch "$config"
	chmod 600 "$config"
fi

# Prepend the Include if absent. It must precede any Host block so its
# `Host *` defaults apply globally (an Include after a Host block is scoped
# to that block).
if ! grep -qF "$include_line" "$config"; then
	tmp="$(mktemp)"
	printf '%s\n\n' "$include_line" >"$tmp"
	cat "$config" >>"$tmp"
	cat "$tmp" >"$config"
	rm -f "$tmp"
	echo "ensure-ssh-include: added Include line to $config"
else
	echo "ensure-ssh-include: Include line already present, nothing to do"
fi
