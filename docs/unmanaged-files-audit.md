# Unmanaged files audit — 2026-09-10

Audited on `dlco-prod`, profile `server`, work role disabled.

## Added to source control

- CER production watcher under `.local/libexec/cer-production/`, its non-secret
  `deploy.env`, and placeholder application/database environment examples.
- Updated the managed CER service and legacy launcher from their live contents
  to preserve the current deployment configuration.
- Restricted all CER configuration, scripts, service, and timer to `dlco-prod`
  with the server profile. No service restart or deployment was performed.
- `.ssh/config`, which includes the already-managed `config.d` snippets.
- `GEMINI.md` was subsequently removed at the user's request; Gemini is no longer used.

## Left unmanaged

- Private keys, cloud credentials, CER credential blobs and backups: operational
  secrets, not portable plaintext dotfiles. CER recovery still requires credentials
  and host provisioning outside this repository.
- Moshi binaries, its generated service, OpenCode/Gemini hooks, and systemd enablement
  links: installer/runtime-owned. Existing managed Moshi setup owns installation.
- Herdr plugin registry, downloads, locks, and sessions: generated installation state.
- `herdr/url_picker.sh`: no reference in the current managed Herdr configuration.
- btop configuration: generated settings with save-on-exit enabled; no clear custom
  policy identified. Empty lazydocker configuration adds no useful configuration.
- Walker and tmux files: desktop leftovers and retired tooling on this server.
- `.bashrc`: explicitly unmanaged under the repository's agent guide.
- Neovim license/readme/gitignore and `argv.json`: upstream metadata and an
  application-generated crash-reporter identifier.
- Installed CLIs, caches, databases, histories, project checkouts, and archives:
  application data or independently managed software.

The full profile-render script currently fails on this server because its Omarchy
render requires `/usr/share/omarchy/config/hypr/hyprland.lua`. Targeted validation
must not be represented as a successful full Omarchy render.
