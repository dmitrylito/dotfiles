# Media services on DLCO-1 and DLCO-3

DLCO-1 (`192.168.0.11`, assigned by router DHCP reservation) owns Plex, Sonarr, Radarr, qBittorrent and Gluetun. Plex retains its Intel device and local video library. qBittorrent retains the Gluetun network namespace and local `/scratch` downloads.

DLCO-3 (`192.168.0.13`) owns Seerr, Prowlarr, FlareSolverr, Homepage, Audiobookshelf, Calibre-Web Automated and Shelfmark. Its application databases and settings are under `/data/docker-appdata`; book libraries are under `/data/media`; Calibre ingest is `/data/media-scratch/calibre-ingest`. Rootless Podman images and container storage live at `/data/containers/storage` on the same dedicated SSD, selected by the host-gated `storage.conf`. Container paths retain `/data/media`, `/scratch/calibre-ingest`, `/calibre-library`, and the Audiobookshelf library paths.

## Dependencies and startup

Shelfmark requires `media-downloads.service`: a read-only SSHFS mount of `dlco-1:/scratch/downloads` at `~/mnt/dlco1-downloads`, bound into Shelfmark at `/scratch/downloads`. Install `sshfs` on DLCO-3 and enable `user_allow_other` in `/etc/fuse.conf` so the rootless container namespace can traverse the read-only mount. The mount parent is private to the owner, with a traversal ACL for host UID 100000 (DLCO-3's container-root subordinate UID). Recheck `/etc/subuid` if that mapping changes. The service refreshes Tailscale's authenticated SSH host keys before mounting. SSHFS reconnects after network interruptions; application databases and the Calibre library never live on this mount. Shelfmark stops when the mount service stops and is started again when the mount is ready. Keep qBittorrent's book downloads under `/scratch/downloads`.

Homepage reads its local Podman socket and `/remote-podman/podman.sock`. `media-podman-tunnel.service` creates the latter through authenticated Tailscale SSH. DLCO-1's `media-podman-proxy.socket` listens only on `127.0.0.1:23750` and forwards to its rootless Podman socket. The tunnel preserves its runtime directory across reconnects so Homepage keeps the same directory bind mount. No Podman API is published to the LAN. Enable the proxy socket on DLCO-1 and the tunnel service on DLCO-3.

`media-downloads.service` and `media-podman-tunnel.service` retry after 30 seconds, with at most ten starts in five minutes. Inspect them with `systemctl --user status` and `journalctl --user -u`. SSHFS startup and shutdown have 30-second limits. Enable lingering for the service account on both hosts.

The per-host `.chezmoiignore` gates Quadlets, the storage configuration and helper units. Ignoring a target does not delete a previously deployed unit: when moving a service, stop it and move its old Quadlet outside every generator search directory, then reload systemd. Never leave two writers using copied application databases.

DLCO-1's pod publishes on `192.168.0.11`; unused publications have no application listener. DLCO-3's pod publishes only its own services.

## Integrations and routing

Prowlarr advertises `https://prowlarr.dlco.us` to Sonarr and Radarr on DLCO-1. Its FlareSolverr proxy uses DLCO-3. Prowlarr and Shelfmark reach qBittorrent at `http://192.168.0.11:8181`. Shelfmark's Calibre navigation link uses `https://calibre.dlco.us`; file imports use the local shared ingest directory. Seerr retains its DLCO-1 Plex/Sonarr/Radarr endpoints.

Homepage's encrypted services configuration is rendered from the chezmoi source into `/data/docker-appdata/homepage` by `scripts/sync-media-homepage.sh` at apply and service startup. The source is ignored as a normal home target on DLCO-3, so a full chezmoi apply will not recreate an obsolete home config. Its widgets assign retained containers to `podman-dlco1`; moved containers use `podman`. The qBittorrent authentication subnet whitelist includes only the two application hosts (`192.168.0.11/32` and `192.168.0.13/32`) for existing dashboard API widgets. Public routing and authentication remain on the proxy.

Cross-host web traffic uses DLCO-3's existing HTTPS port. Its Caddy forwards locally to the pod; Caddy on the other nodes forwards the moved sites to `https://192.168.0.13` with each site's TLS server name. Direct application ports remain blocked by the existing firewall; no additional firewall rules are needed.

Change only the moved-service Caddy upstreams: ports 3000, 5055, 9696, 13378, 8084 and 8085. Do not activate keepalived or migrate the front door as part of a media move.

## Verification

Run `scripts/test-templates.sh`, inspect each host's Quadlet generator output, and check container health. Verify both Homepage socket endpoints, the read-only download mount from inside Shelfmark, Prowlarr's application/indexer addresses, Seerr's existing integrations, Calibre's library database and initialization scripts, and public proxy routes. A health check alone does not prove download/import functionality.

References: [Podman 6.1.2 Quadlets](https://docs.podman.io/en/v6.1.2/markdown/podman-systemd.unit.5.html), [Shelfmark storage](https://github.com/calibrain/shelfmark/blob/main/docs/configuration.md), [Homepage Docker connections](https://gethomepage.dev/configs/docker/).
