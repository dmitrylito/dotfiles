#!/usr/bin/env bash
# Emit Homepage service groups (YAML list items) for every `@name host …` site in a rendered Caddyfile.
# Usage: homepage-caddy-services.sh [/path/to/Caddyfile]   (default: ~/docker-appdata/caddy/Caddyfile)
# `*.dlco.us` sites become the "Public" group, `*.init.dlco.us` sites the "Internal" group; each card links
# to the first host (or the `prefer` override, with an optional `paths` suffix), shows the hostname(s), and gets a
# siteMonitor on that host. Stdout is appended to
# services.yaml by sync-media-homepage.sh, so keep the output a top-level YAML list.
set -euo pipefail
caddyfile=${1:-$HOME/docker-appdata/caddy/Caddyfile}
awk '
function icon(name) {
    if (name in icons) return icons[name]
    return "mdi-web"
}
function flush_group() {
    if (count == 0) return
    print "- " group ":"
    printf "%s", body
    body = ""; count = 0
}
BEGIN {
    icons["audiobooks"] = "audiobookshelf.png"; icons["books"] = "calibre-web.png"; icons["calibre"] = "calibre-web.png"
    icons["plex"] = "plex.png"; icons["prowlarr"] = "prowlarr.png"; icons["radarr"] = "radarr.png"; icons["sonarr"] = "sonarr.png"
    icons["seerr"] = "overseerr.png"; icons["home"] = "homepage.png"; icons["vsl"] = "supabase.png"; icons["torrent"] = "qbittorrent.png"
    icons["adguard"] = "adguard-home.png"; icons["kuma"] = "uptime-kuma.png"; icons["omada"] = "omada.png"
    icons["dlco1"] = "cockpit.png"; icons["dlco2"] = "cockpit.png"; icons["dlco3"] = "cockpit.png"
    icons["cer"] = "mdi-office-building"; icons["cer-staging"] = "mdi-office-building-outline"; icons["backend"] = "mdi-api"
    icons["billing"] = "mdi-cash-multiple"; icons["chat"] = "mdi-chat-outline"; icons["console"] = "mdi-console"
    icons["fcbot"] = "mdi-robot-outline"; icons["liveevents"] = "mdi-broadcast"
    prefer["kuma"] = "uptime.init.dlco.us"
    paths["cer"] = "/admin"; paths["cer-staging"] = "/admin"
}
/^\*\.dlco\.us \{/ { flush_group(); group = "Public"; next }
/^\*\.init\.dlco\.us \{/ { flush_group(); group = "Internal"; next }
/^\}/ { flush_group(); group = ""; next }
group != "" && $1 ~ /^@/ && $2 == "host" {
    name = substr($1, 2); primary = $3; extra = ""
    if (name in prefer) primary = prefer[name]
    else for (i = 4; i <= NF; i++) extra = extra (extra == "" ? "" : ", ") $i
    pending = name; hosts[name] = primary; extras[name] = extra; next
}
group != "" && pending != "" && $1 == "reverse_proxy" {
    desc = hosts[pending]; if (extras[pending] != "") desc = desc " · " extras[pending]
    path = (pending in paths) ? paths[pending] : ""
    body = body sprintf("    - %s:\n        id: caddy-%s\n        icon: %s\n        href: https://%s%s\n        description: %s\n        siteMonitor: https://%s\n", pending, pending, icon(pending), hosts[pending], path, desc, hosts[pending])
    count++; pending = ""
}
' "$caddyfile"
