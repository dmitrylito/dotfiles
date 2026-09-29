#!/usr/bin/env bash
# Emit a Homepage "Stacks" service group (YAML list item): one card per docker compose project and per Podman pod,
# on this host and on DLCO-1 through the media-podman-tunnel socket. Stdout is appended to services.yaml by
# sync-media-homepage.sh, so the snapshot refreshes when Homepage (re)starts or the chezmoi source changes.
set -euo pipefail
remote_sock=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/media-remote/podman.sock
host=$(hostname)
declare -A hrefs=([prod]=https://cer.dlco.us [supabase]=https://vsl.dlco.us [caddy]=https://home.dlco.us)
declare -A icons=([prod]=mdi-office-building [supabase]=supabase.png [caddy]=caddy.png [media]=mdi-multimedia)
card() {
    local name=$1 count=$2 where=$3 engine=$4 server=$5 container=$6
    local id="stack-${where,,}-${name%% *}"
    printf '    - %s:\n        id: %s\n        icon: %s\n        description: %s containers · %s · %s\n' "$name" "$id" "${icons[${name%% *}]:-mdi-layers-outline}" "$count" "$engine" "$where"
    [[ -n ${hrefs[${name%% *}]:-} ]] && printf '        href: %s\n        siteMonitor: %s\n' "${hrefs[${name%% *}]}" "${hrefs[${name%% *}]}"
    [[ -n $container ]] && printf '        server: %s\n        container: %s\n' "$server" "$container"
    return 0
}
echo "- Stacks:"
docker ps --format '{{.Label "com.docker.compose.project"}}' 2>/dev/null | grep -v '^$' | sort | uniq -c |
    while read -r count name; do card "$name" "$count" "$host" "docker compose" "" ""; done
podman ps --format '{{.PodName}}' 2>/dev/null | grep -v '^$' | sort | uniq -c |
    while read -r count name; do card "$name" "$((count - 1))" "$host" "podman pod" podman "$name-infra"; done
if [[ -S $remote_sock ]]; then
    podman --url "unix://$remote_sock" ps --format '{{.PodName}}' 2>/dev/null | grep -v '^$' | sort | uniq -c |
        while read -r count name; do card "$name (DLCO-1)" "$((count - 1))" "DLCO-1" "podman pod" podman-dlco1 "$name-infra"; done
fi
