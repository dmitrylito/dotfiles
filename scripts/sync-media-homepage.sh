#!/usr/bin/env bash
# Render Homepage's managed config into DLCO-3's /data bind mount. Run from the chezmoi hook or Homepage ExecStartPre.
# Requires DLCO-3, mounted /data, the chezmoi age identity, and this source checkout; leaves existing files intact on failure.
set -euo pipefail
[[ $(hostname) == DLCO-3 ]]
[[ $(findmnt -n -o UUID -T /data) == 18ac3a4e-e866-434a-b664-98ef8e9486e2 ]]
source_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
target_dir=/data/docker-appdata/homepage
mkdir -p "$target_dir"
umask 077
stage_dir=$(mktemp -d "$target_dir/.sync.XXXXXXXX")
trap 'rm -rf -- "$stage_dir"' EXIT
chezmoi decrypt "$source_dir/docker-appdata/homepage/encrypted_private_services.yaml.age" > "$stage_dir/services.yaml"
cp "$source_dir/docker-appdata/homepage/docker.yaml" "$stage_dir/docker.yaml"
chmod 0600 "$stage_dir/services.yaml"
chmod 0644 "$stage_dir/docker.yaml"
for name in services.yaml docker.yaml; do
    if cmp -s "$stage_dir/$name" "$target_dir/$name"; then
        rm "$stage_dir/$name"
    else
        mv -f "$stage_dir/$name" "$target_dir/$name"
    fi
done
