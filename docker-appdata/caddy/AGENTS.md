# Caddy reverse proxy (dlco-1, dlco-2, dlco-3)

Every public `*.dlco.us` and Tailscale `*.init.dlco.us` site is served by Caddy running
identically on all three servers. keepalived moves the LAN VIP `192.168.0.3` (the router's
80/443 forward target) to a healthy node, so any one box can go down. This replaced Nginx
Proxy Manager on DLCO-2.

- Source of truth is chezmoi: `docker-appdata/caddy/` in `~/.local/share/chezmoi`. Never edit
  the deployed copy in `~/docker-appdata/caddy/`.
- Add or change a site in `Caddyfile.tmpl` as a `@name host …` + `handle` pair inside the
  matching wildcard block. Keep sites inside the wildcard blocks: per-host site blocks issue a
  certificate per name per node and hit Let's Encrypt's 50-per-week domain limit.
- Backend IPs are the variables at the top of `Caddyfile.tmpl`; change them there.
- Per-node keepalived settings (interface, node IP, priority) are the `$nodes` map in
  `keepalived/keepalived.conf.tmpl`.
- The Cloudflare token comes from the `caddy` group of `.secrets.yaml.age` (`secrets-edit`),
  rendered to `~/.config/secrets/caddy.env`. It needs Zone:Read and DNS:Edit on `dlco.us`.

Deploy to one node (repeat per node; do them one at a time so the VIP always has a holder):

    chezmoi apply ~/docker-appdata/caddy ~/.config/secrets/caddy.env
    cd ~/docker-appdata/caddy && docker compose up -d --build
    docker compose exec caddy caddy validate --config /etc/caddy/Caddyfile

After a `Caddyfile` edit, recreate only Caddy and validate it:

    chezmoi apply ~/docker-appdata/caddy/Caddyfile
    cd ~/docker-appdata/caddy && docker compose up -d --no-deps --force-recreate caddy
    docker compose exec caddy caddy validate --config /etc/caddy/Caddyfile

Chezmoi replaces the rendered file atomically. Docker's single-file bind mount keeps pointing
at the old inode until the Caddy container is recreated; `caddy reload` alone reads the old file.

Check a node directly, bypassing the VIP:

    curl -sI --resolve radarr.dlco.us:443:192.168.0.11 https://radarr.dlco.us/

`ip -4 addr show | grep 192.168.0.3` shows which node holds the VIP.
