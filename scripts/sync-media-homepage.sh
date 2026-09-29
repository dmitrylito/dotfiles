#!/usr/bin/env bash
# Render Homepage's managed config into DLCO-3's /data bind mount. Run from the chezmoi hook or Homepage ExecStartPre.
# Requires DLCO-3, mounted /data, the chezmoi age identity, this source checkout, and the rendered Caddyfile at
# ~/docker-appdata/caddy/Caddyfile (its sites become the Public/Internal groups). Leaves existing files intact on failure.
set -euo pipefail
[[ $(hostname) == DLCO-3 ]]
[[ $(findmnt -n -o UUID -T /data) == 18ac3a4e-e866-434a-b664-98ef8e9486e2 ]]
source_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
homepage_src=$source_dir/docker-appdata/homepage
target_dir=/data/docker-appdata/homepage
mkdir -p "$target_dir"
umask 077
stage_dir=$(mktemp -d "$target_dir/.sync.XXXXXXXX")
trap 'rm -rf -- "$stage_dir"' EXIT
gen=$source_dir/scripts/homepage-caddy-services.sh
{
    cat "$homepage_src/services-status.yaml"
    echo "- Media:"
    chezmoi decrypt "$homepage_src/encrypted_private_services.yaml.age" | sed 's/^/    /'
    "$gen" Media
    echo "- Management:"
    cat "$homepage_src/services-management.yaml"
    "$gen" Management
    echo "- Personal:"
    "$gen" Personal
    echo "- Work:"
    "$gen" Work
} > "$stage_dir/services.yaml"
chmod 0600 "$stage_dir/services.yaml"
plain=(docker.yaml settings.yaml widgets.yaml bookmarks.yaml custom.css)
for name in "${plain[@]}"; do
    cp "$homepage_src/$name" "$stage_dir/$name"
    chmod 0644 "$stage_dir/$name"
done
for name in services.yaml "${plain[@]}"; do
    if cmp -s "$stage_dir/$name" "$target_dir/$name"; then
        rm "$stage_dir/$name"
    else
        mv -f "$stage_dir/$name" "$target_dir/$name"
    fi
done
