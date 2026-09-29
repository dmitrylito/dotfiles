#!/usr/bin/env bash
# Emit Homepage service cards (YAML list items, indented for one group) for the `@name host …` sites of a rendered
# Caddyfile that belong to one category.
# Usage: homepage-caddy-services.sh <Media|Management|Personal|Work> [/path/to/Caddyfile]
# Default Caddyfile: ~/docker-appdata/caddy/Caddyfile. Each card links to the first host (or the `prefer` override
# plus an optional `paths` suffix), shows the hostname(s), and gets a siteMonitor on that same URL. Sites in `skip`
# already have a widget card in the encrypted services file. sync-media-homepage.sh places the output under the group.
set -euo pipefail
category=$1
caddyfile=${2:-$HOME/docker-appdata/caddy/Caddyfile}
awk -v want="$category" '
function icon(name) {
    if (name in icons) return icons[name]
    return "mdi-web"
}
BEGIN {
    cat["audiobooks"] = "Media"; cat["books"] = "Media"; cat["calibre"] = "Media"; cat["plex"] = "Media"; cat["seerr"] = "Media"
    cat["adguard"] = "Management"; cat["dlco1"] = "Management"; cat["dlco2"] = "Management"; cat["dlco3"] = "Management"
    cat["kuma"] = "Management"; cat["omada"] = "Management"
    cat["chat"] = "Personal"
    cat["backend"] = "Work"; cat["billing"] = "Work"; cat["cer"] = "Work"; cat["cer-staging"] = "Work"; cat["console"] = "Work"
    cat["fcbot"] = "Work"; cat["liveevents"] = "Work"; cat["vsl"] = "Work"
    skip["home"] = 1; skip["sonarr"] = 1; skip["radarr"] = 1; skip["prowlarr"] = 1; skip["torrent"] = 1
    icons["audiobooks"] = "audiobookshelf.png"; icons["books"] = "calibre-web.png"; icons["calibre"] = "calibre-web.png"
    icons["plex"] = "plex.png"; icons["seerr"] = "overseerr.png"; icons["vsl"] = "supabase.png"
    icons["adguard"] = "adguard-home.png"; icons["kuma"] = "uptime-kuma.png"; icons["omada"] = "omada.png"
    icons["dlco1"] = "cockpit.png"; icons["dlco2"] = "cockpit.png"; icons["dlco3"] = "cockpit.png"
    icons["cer"] = "mdi-office-building"; icons["cer-staging"] = "mdi-office-building-outline"; icons["backend"] = "mdi-api"
    icons["billing"] = "mdi-cash-multiple"; icons["chat"] = "mdi-chat-outline"; icons["console"] = "mdi-console"
    icons["fcbot"] = "mdi-robot-outline"; icons["liveevents"] = "mdi-broadcast"
    prefer["kuma"] = "uptime.init.dlco.us"; prefer["fcbot"] = "ops.dlco.us"
    paths["cer"] = "/admin"; paths["cer-staging"] = "/admin"; paths["fcbot"] = "/admin/"
}
/^\*\.dlco\.us \{/ || /^\*\.init\.dlco\.us \{/ { inblock = 1; next }
/^\}/ { inblock = 0; next }
inblock && $1 ~ /^@/ && $2 == "host" {
    name = substr($1, 2); primary = $3; extra = ""
    if (name in prefer) primary = prefer[name]
    else for (i = 4; i <= NF; i++) extra = extra (extra == "" ? "" : ", ") $i
    pending = name; hosts[name] = primary; extras[name] = extra; next
}
inblock && pending != "" && $1 == "reverse_proxy" {
    name = pending; pending = ""
    if (name in skip) next
    group = (name in cat) ? cat[name] : "Personal"
    if (group != want) next
    desc = hosts[name]; if (extras[name] != "") desc = desc " · " extras[name]
    path = (name in paths) ? paths[name] : ""
    printf "    - %s:\n        id: caddy-%s\n        icon: %s\n        href: https://%s%s\n        description: %s\n        siteMonitor: https://%s%s\n", name, name, icon(name), hosts[name], path, desc, hosts[name], path
}
' "$caddyfile"
