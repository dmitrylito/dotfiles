#!/usr/bin/env bash
# Emit Homepage service cards (YAML list items, indented for one group) for the `@name host …` sites of a rendered
# Caddyfile that belong to one category.
# Usage: homepage-caddy-services.sh <Media|"Home & Network"|Servers|Personal|Work> [/path/to/Caddyfile]
# Default Caddyfile: ~/docker-appdata/caddy/Caddyfile. Each card links to the first host (or the `prefer` override
# plus an optional `paths` suffix), shows the hostname(s), and gets a siteMonitor on that same URL. Sites in `skip`
# already have a widget card elsewhere. Cards with a `rank` come first (lowest first); the rest keep Caddyfile order.
# sync-media-homepage.sh places the output under the group.
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
    cat["adguard"] = "Home & Network"; cat["omada"] = "Home & Network"; cat["ha"] = "Home & Network"
    cat["dlco1"] = "Servers"; cat["dlco2"] = "Servers"; cat["dlco3"] = "Servers"
    cat["chat"] = "Work"; cat["cer"] = "Personal"; cat["cer-staging"] = "Personal"; cat["vsl"] = "Personal"
    cat["backend"] = "Work"; cat["billing"] = "Work"; cat["console"] = "Work"
    cat["fcbot"] = "Work"; cat["liveevents"] = "Work"
    skip["home"] = 1; skip["sonarr"] = 1; skip["radarr"] = 1; skip["prowlarr"] = 1; skip["torrent"] = 1; skip["kuma"] = 1
    icons["audiobooks"] = "audiobookshelf.png"; icons["books"] = "shelfmark.png"; icons["calibre"] = "calibre-web.png"
    icons["plex"] = "plex.png"; icons["seerr"] = "overseerr.png"; icons["vsl"] = "supabase.png"
    icons["adguard"] = "adguard-home.png"; icons["ha"] = "home-assistant.png"; icons["omada"] = "omada.png"
    icons["dlco1"] = "cockpit.png"; icons["dlco2"] = "cockpit.png"; icons["dlco3"] = "cockpit.png"
    icons["cer"] = "mdi-office-building"; icons["cer-staging"] = "mdi-office-building-outline"; icons["backend"] = "mdi-api"
    icons["billing"] = "mdi-cash-multiple"; icons["chat"] = "mdi-chat-outline"; icons["console"] = "mdi-console"
    icons["fcbot"] = "mdi-robot-outline"; icons["liveevents"] = "mdi-broadcast"
    prefer["fcbot"] = "ops.dlco.us"
    label["fcbot"] = "Ops Center"; label["ha"] = "Home Assistant"; label["adguard"] = "AdGuard Home"; label["omada"] = "Omada"
    label["plex"] = "Plex"; label["seerr"] = "Seerr"; label["audiobooks"] = "Audiobookshelf"; label["books"] = "Shelfmark"
    label["calibre"] = "Calibre"; label["dlco1"] = "DLCO-1 Cockpit"; label["dlco2"] = "DLCO-2 Cockpit"
    label["dlco3"] = "DLCO-3 Cockpit"; label["cer"] = "CER Admin"; label["cer-staging"] = "CER Admin (staging)"
    label["vsl"] = "VSL"; label["backend"] = "Backend"; label["billing"] = "Billing"; label["chat"] = "Chat"
    label["console"] = "Console"; label["liveevents"] = "Live Events"
    rank["plex"] = 1; rank["seerr"] = 2; rank["ha"] = 1; rank["fcbot"] = 1; rank["cer"] = 1; rank["cer-staging"] = 2
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
    title = (name in label) ? label[name] : name
    n++; ord[n] = (name in rank) ? rank[name] : 50
    card[n] = sprintf("    - %s:\n        id: caddy-%s\n        icon: %s\n        href: https://%s%s\n        description: %s\n        siteMonitor: https://%s%s\n", title, name, icon(name), hosts[name], path, desc, hosts[name], path)
}
END {
    for (i = 1; i <= n; i++) {
        best = 0
        for (j = 1; j <= n; j++) if (!(j in done) && (best == 0 || ord[j] < ord[best])) best = j
        done[best] = 1; printf "%s", card[best]
    }
}
' "$caddyfile"
