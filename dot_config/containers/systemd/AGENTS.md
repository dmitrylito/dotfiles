# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Podman **Quadlet** units (`.container`, `.pod`) in the rootless user directory
`~/.config/containers/systemd/`. systemd's `podman-system-generator` reads these
at `daemon-reload` and generates transient `*.service` units. There is no build,
lint, or test step — editing a unit and reloading is the entire workflow.

## Workflow

```sh
# After editing any .container / .pod file:
systemctl --user daemon-reload

# Validate that the generator accepts the units (prints generated .service files):
/usr/lib/podman/quadlet -user -dryrun

# A unit named foo.container becomes foo.service:
systemctl --user start qbittorrent.service
systemctl --user restart media-pod.service     # the pod unit is <PodName>-pod.service
journalctl --user -u plex.service -f

# Pull updated images for AutoUpdate=registry units:
systemctl --user start podman-auto-update.service
```

Note: lingering must be enabled (`loginctl enable-linger dmitrylito`) for these
user services to run without an active login session.

## Architecture

Two networking domains — get this wrong and containers can't reach each other:

1. **`media.pod`** — most services join this shared pod (`Pod=media.pod`) and
   share its network namespace. Ports are published **only** on the pod
   (`media.pod`), bound to the LAN IP `192.168.0.2`, never on the individual
   containers. Members: homepage(3000), seerr(5055), plex(32400), sonarr(8989),
   radarr(7878), prowlarr(9696), flaresolverr(8191), audiobookshelf(13378),
   calibre-web(8084->8083), shelfmark(8085). To expose a new pod
   service, add its `PublishPort=192.168.0.2:<port>:<port>` line to `media.pod`, not the
   container.
   Adding a port there **recreates the pod**, which stops every member; bring them
   back with `systemctl --user restart media-pod.service`, then start each member
   service.

2. **gluetun + qbittorrent VPN namespace** — these are deliberately **outside**
   the pod. `gluetun` runs the ProtonVPN WireGuard tunnel; `qbittorrent` uses
   `Network=container:gluetun` so all its traffic is forced through the VPN and
   it has no network identity of its own. Consequences:
   - qbittorrent's WebUI port (8181) is published by **gluetun**, not qbittorrent.
   - qbittorrent has `Requires=`/`After=gluetun.service` (no `network-online.target`).
   - If qbittorrent can't be reached, check gluetun first.

`minecraft.container` is standalone with **no `[Install]` section** — it is
intentionally not wired to `default.target` and won't start on boot. Start on
demand: `systemctl --user start minecraft.service`.

## Conventions & gotchas

- **UID mapping under `UserNS=keep-id`**: container uid 1000 maps to host
  `dmitrylito`. `homepage` must run as `PUID/PGID=1000` so it can read the mounted
  Podman socket (`%t/podman/podman.sock`); running as root maps to a subuid that
  cannot, breaking the docker.yaml stats integration. The *arr services run as
  `PUID/PGID=0` by contrast.
- **`keep-id` breaks any LSIO image that needs root.** keep-id forces
  `User=1000:1000`, and a non-root LSIO container disables both
  `/custom-cont-init.d` and `DOCKER_MODS` ("custom services & docker mod
  functionality will be disabled") while `s6-applyuidgid` fatal-loops on
  `setgroups` — the app never binds its port. The *arr units survive only because
  they use neither feature. `calibre-web` needs both, so it sets **`UserNS=host`**:
  that keeps the pod's network namespace but restores container root, which under
  rootless podman still maps to host `dmitrylito` (verified), so files stay
  host-owned. With `UserNS=host` its PUID/PGID must be **0** — uid 1000 would land
  on an unmapped subuid and lock the host out of `/config`.
- **qbittorrent is no longer pinned** (2026-08-17). It sat on 4.6.7 to dodge Prowlarr
  failing to add a qBittorrent download client, but that was a Prowlarr bug, not a qbit
  one -- it threw the same `NullReferenceException` in `ValidateCategories` on 4.6.7 and
  5.2.1 alike. Prowlarr 2.5.2 no longer throws it, verified against this box, so the unit
  is back on `:latest` (now 5.2.3). Gluetun publishes the qBittorrent WebUI on host
  port `8181` for the existing protected proxy path. Radarr, Sonarr, Shelfmark, and
  other local integrations reach it at `172.17.0.1:8181` or `192.168.0.2:8181`.
  The `WebUI\AuthSubnetWhitelist` covers only `192.168.0.2/32`; remote clients still
  authenticate through the existing front-end access controls.
- **Storage layout**: app config under `/home/dmitrylito/docker-appdata/<svc>`,
  media under `/data/media`, download scratch under `/scratch`. Plex transcodes to
  `/dev/shm` (RAM). ZFS volume mounts use `:Z` (private relabel) for config and
  `:z` (shared relabel) for media paths shared across the *arr stack.
- **Secrets do not live inline.** `gluetun.container` loads its WireGuard key from
  `~/.config/containers/systemd/secrets/gluetun.env`. Chezmoi stores that file with
  age encryption and deploys it with mode `0600`.
- Every media container has an application-level Podman health check. Validate the
  whole stack with `podman ps --format '{{.Names}} {{.Status}}'` after changes.
