# Dmitry's dotfiles

Chezmoi manages one shared configuration across `omarchy`, `server`, and `mac`
profiles. A separate `work` role enables Fleet Chaser tooling without encoding
work ownership in a hostname. The source of truth is this directory; do not edit
managed targets in `$HOME` directly.

Agents working on this source repository should read [.claude/AGENTS.md](.claude/AGENTS.md).

## Bootstrap and safe daily use

```bash
sh -c "$(curl -fsLS get.chezmoi.io)" -- init --apply dmitrylito
cd "$(chezmoi source-path)"
chezmoi apply
chezmoi status
chezmoi diff
chezmoi apply --dry-run -v
```

Initialization asks for a platform profile and whether the machine has the work
role. `ce <target>` is the shell alias for `chezmoi edit --apply <target>`.
Chezmoi auto-commits and pushes source changes made through its commands. Plain
editor writes remain dirty until committed deliberately; package reconciliation
does not generate commits.

## Configuration dimensions

| Profile | Platform layer | Shared layer |
|---|---|---|
| `omarchy` | Hyprland, Omarchy shell, Linux desktop apps | shell, editor, Herdr, Moshi, AI tooling |
| `server` | headless Arch packages and user services | shell, editor, Herdr/Moshi support |
| `mac` | AeroSpace, SketchyBar, Borders, macOS apps | shell, editor, Herdr/Moshi clients |

`work = true` adds the Fleet Chaser project environment, mypy/import helpers,
Claude work skills, work launchers, and the Omarchy work layout. `.chezmoiignore`
is the single deployment boundary for both profile and role.

## Package reconciliation

Package reconciliation runs automatically after `chezmoi init` or `apply` when
the playbook, reconciliation script, active profile, role, or active machine's
actionable package lists change. A no-op apply does not rerun Ansible. You can
also invoke it explicitly:

```bash
scripts/update_package_lists.sh   # regenerate the current Omarchy host inventory
scripts/reconcile-packages.sh --check
scripts/reconcile-packages.sh     # install declared and remove removed.txt entries
```

When automatic reconciliation is triggered on Linux, chezmoi may ask for sudo.
The Ansible playbook:

- installs packages listed for the active profile;
- installs Oh My Zsh and clones Zsh Sage plus the other external plugins;
- removes only names explicitly placed in an Omarchy host's `removed.txt`;
- on `server`, removes undeclared explicit packages while retaining required
  dependencies and canonicalizing their install reason;
- on `omarchy`, never infers removals from absence or sweeps dependencies;
- treats Omarchy base/other/driver snapshots as reference data only;
- temporarily permits the AUR build user to invoke `/usr/bin/pacman`, not an
  unrestricted root command.

See `packages/README.md` for list ownership and regeneration rules.

Server profiles also install a Pacman post-transaction publisher and two
15-minute retry/convergence timers. A manual install or removal is regenerated,
committed, and pushed after the transaction; the other server pulls the
committed declarations and converges under a root-owned worker. A runtime marker
prevents reconciliation transactions from being published back as new intent.

## Major subsystems

- `.chezmoi.toml.tmpl` and `.chezmoiignore`: profile/role selection and target
  routing.
- `dot_zshenv.tmpl`, `dot_zshrc.tmpl`, `dot_aliases.tmpl`: shared environment,
  interactive shell, and role-gated aliases.
- `dot_config/mise/config.toml.tmpl`: authoritative runtimes and CLI tools,
  including `agy` on all three profiles; server Codex remains native-owned.
- `dot_config/herdr/`: universal terminal workspace/multiplexer. tmux,
  Tmuxifier, and sesh are intentionally retired.
- `dot_local/bin/moshi-*`, Moshi hook modifiers, and Linux user units: keep
  Claude/Codex conversations bound to the correct Herdr pane. macOS receives
  the guards and config. Linux bootstraps the vendor binary, agent hooks,
  encrypted pairing token, and systemd user service during `chezmoi apply`;
  macOS service setup remains Homebrew-owned.
- `dot_config/nvim/`: LazyVim configuration, Sidekick integration, and the
  Neovim remote clipboard implementation. Shell `ff`/`yf` use the managed
  `clipboard-copy` helper for local Wayland/macOS and terminal OSC 52 copying.
- `dot_config/hypr/` and `dot_config/omarchy/`: Omarchy-only desktop behavior.
  The Hyprland entrypoint is derived from Omarchy's installed default by a
  `modify_` script; chezmoi owns only the post-default `hypr.chezmoi` module.
- `dot_config/aerospace/`, `dot_config/sketchybar/`, `dot_config/borders/`:
  macOS-only desktop behavior.
- `dot_claude/`, `dot_codex/`, `dot_config/opencode/`: agent settings, hooks,
  rules, and plugins.
- `Projects/fleetchaser/`, Fleet Chaser helpers/skills, work launchers, and
  `work-mode`: work-role-only configuration.

## Local binary ownership

`docs/local-bin-audit.md` records the audited `~/.local/bin` categories, their
owners, consumers, and subsequent migrations. New custom scripts should be
added under `dot_local/bin/executable_*`; vendor binaries stay vendor-owned and
CLI tools should be declared in mise instead of wrapped by ad-hoc scripts.

## Validation before applying

Validate all six profile/role combinations plus four hostname-specific cases,
then preview only the intended targets on the active machine:

```bash
scripts/test-templates.sh
chezmoi apply --dry-run -v ~/.aliases ~/.zshrc
```

The dry run matters because live target drift can be intentional. A global
apply should not be used to erase drift that was not part of the current task.

The validator uses disposable configuration, a generated age identity, and
nonsecret fixtures. It runs modifiers, but never deployment hooks. See
[docs/validation.md](docs/validation.md) for prerequisites, coverage, and the
optional check against installed Omarchy.

A fresh GitHub mirror audited on 2026-09-18 contained 6.97 MiB of packed objects,
no Elephant paths, and no blobs over 10 MiB. No remote history rewrite is needed.
See [docs/git-history-audit.md](docs/git-history-audit.md) for scope and evidence;
the size of an existing local `.git` directory is not the fresh-clone size.
