# `~/.local/bin` audit — 2026-08-31

This inventory distinguishes source-managed scripts, vendor binaries, mise
launchers, and confirmed debris. “Keep” does not mean Chezmoi should copy a
large vendor binary; it means its owner and consumer are known.

## Chezmoi-managed custom scripts

| Command | Purpose | Scope/consumer | Decision |
|---|---|---|---|
| `chezmoi-autoupdate` | throttled pull/apply helper | interactive Zsh | keep |
| `chromium-profile-launch` | resolves named Chromium profiles and web apps | Omarchy launchers | keep |
| `claude-prune-agents` | prunes stale completed agent entries | Linux timer | keep |
| `discord-ptm` | Discord push-to-mute | Omarchy keybind | keep |
| `fc-mypy`, `fc-dmypy` | Django-aware mypy wrappers | work role, Neovim | keep |
| `herdr-remote-picker` | chooses an SSH target for Herdr | Omarchy/mac keybind | keep |
| `import-db` | refreshes local Fleet Chaser DB from production dump | work role | keep; newly managed |
| `moshi-hook-claude-guard` | prevents tty-less Claude jobs stealing Herdr panes | Moshi hooks | keep |
| `moshi-hook-codex-guard` | invokes Moshi and repairs Codex/Herdr identity | Moshi hooks | keep |
| `moshi-pane-rebind` | reconciles Herdr panes to Claude/Codex sessions | Linux timer/hooks | keep |
| `omarchy-lock-dpms-guard` | keeps hot-plug monitors dark while locked | Omarchy service | keep |
| `work-mode` | restores the Fleet Chaser desktop layout | work role | keep |

## Vendor/tool-manager owned

| Command | Owner and use | Decision |
|---|---|---|
| `agy` | Antigravity CLI, now declared in managed Mise config on all profiles | migrated from vendor ownership on 2026-09-18; see below |
| `herdr` 0.8.2 | primary universal multiplexer and agent workspace | keep; vendor binary |
| `moshi-hook` 0.2.59 and `moshi` symlink | Moshi gateway/hook client | keep; vendor binary |
| `pass-cli` 2.2.3 | Proton Pass CLI; secrets/doctor integration | keep; vendor binary |
| `spotify-cli` | uv-tool symlink | keep; owned by uv |
| `claude`, `codex`, `gh`, `grok`, `hey`, `node`, `opencode`, `pi` | installed and activated by managed mise config | keep; no local wrapper |

## Removed to Trash

- `agy.1781553305300649075.old` — 160 MiB obsolete copy of `agy`.
- `import-db.bak.20260723162020` — superseded unmanaged backup.
- `moshi-codex-hook` — old wrapper replaced by the managed guard.
- `hypr-resize` — unreferenced helper.
- `install-dp2-lock-binding`, `omarchy-system-lock.broken-dp2`, the enabled
  `dp2-lock-binding.service`, and `~/.config/hypr/scripts/lock.sh` — incomplete
  DP-2 workaround superseded by `omarchy-lock-dpms-guard`.
- old `omarchy-recover-internal-monitor` upgrade backup unit.
- `claude`, `codex`, `copilot`, `crush`, `gh`, `ghui`, `grok`, `hey`, `hunk`,
  `omp`, `opencode`, `ori`, `pi`, and `playwright` wrapper scripts — AI/Herdr-
  generated `mise use -g` launchers. The `gh` wrapper recursively invoked mise,
  spawned repeated processes, and left temp config files. Configured tools now
  come directly from mise; unconfigured experiments were retired.
- `.config/mise/.config.toml.*` — leftovers from those recursive concurrent writes.

The DP-2 service was disabled before its files were trashed. These items remain
recoverable from the desktop Trash until it is emptied.

## Mise ownership update — 2026-09-18

`agy = "latest"` now belongs to `dot_config/mise/config.toml.tmpl`. The temporary
declaration in root `mise.toml` was removed, including from its deployed
`~/mise.toml` target. On the audited desktop, Mise resolves `agy` from
`~/.config/mise/config.toml`; the CLI reports version 1.2.6, while Mise's installed
artifact directory is named 1.2.5.

The previous `~/.local/bin/agy` 1.0.8 executable was moved to
`~/.local/state/chezmoi/backups/agy-20260918T101233/agy`, preserving rollback while
removing PATH shadowing. Other hosts should apply the two Mise targets, run
`mise install agy`, verify `mise exec agy -- agy --version`, and check for an old
vendor executable before retiring it. This local migration did not change other hosts.
