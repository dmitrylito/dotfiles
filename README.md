# Dmitry's dotfiles

Chezmoi manages one shared configuration across `omarchy`, `server`, and `mac`
profiles. A separate `work` role enables Fleet Chaser tooling without encoding
work ownership in a hostname. The source of truth is this directory; do not edit
managed targets in `$HOME` directly.

Agents working on this source repository should read [.claude/AGENTS.md](.claude/AGENTS.md).

## Set up a new Arch server

Install chezmoi, then run **one command** as your normal login user:

```bash
chezmoi init --apply dmitrylito
```

Choose `server` and whether this machine needs the Fleet Chaser work configuration.
Basic internet connectivity and working sudo access are the starting prerequisites.
You do not need Ansible, Git, a running SSH daemon, or the age key beforehand.
Chezmoi uses its built-in Git implementation when Git is absent.

The server bootstrap continues through these stages automatically:

1. Install Git, Ansible, Python/uv, OpenSSH, Tailscale, and bootstrap dependencies.
2. Enable and start `sshd` and `tailscaled`, and enable the systemd user manager
   after logout. Open Tailscale's printed login URL to add the machine to your network.
3. Install the shared server packages, Oh My Zsh, shell plugins, mise tools,
   Neovim through Bob, Herdr, and native Codex. Existing native Herdr/Codex
   binaries are retained.
4. Guide GitHub browser authentication for background Git synchronization and
   configure a missing commit identity from the authenticated GitHub account.
5. Print the exact Taildrop command to run on dlco to send the age key. Press
   Enter after sending it; bootstrap receives it, installs it privately, and
   verifies decryption. No SSH-key exchange is needed.
6. Continue the same chezmoi invocation to apply your managed shell, editor,
   agent settings, private configuration, and deployment hooks. Then select Zsh
   as your login shell and verify SSH, Tailscale, Moshi, and package-sync timers.

Log out and back in afterward; `cz` is then available as an alias for `chezmoi`.
Claude/Codex account login remains an application-level first-use action.

### Encryption-key transfer

The bootstrap prints this command with the new server's actual Tailscale IP.
Run it on **dlco** when prompted:

```bash
sudo tailscale file cp ~/.config/chezmoi/key.txt NEW_SERVER:
```

Taildrop requires Send Files enabled in the tailnet and both devices owned by
**the same Tailscale user**, without tags. If Taildrop is unavailable, transfer
the existing identity to `~/.config/chezmoi/key.txt` on the new server by another
secure method before pressing Enter. Starting `sshd` does not itself grant access;
normal SSH still needs a permitted password/key, or use Tailscale SSH with an
allowing policy. The bootstrap does not copy dlco's SSH host keys or machine identity.

A newly generated age key cannot decrypt this repository. Keep the existing
identity outside Git; never paste it into logs or chat. An existing key is not
overwritten. If it cannot decrypt the baseline, setup stops for correction.

### Already-installed software

Bootstrap dependencies use Pacman's `--needed`, and Ansible computes missing
native/AUR packages from the installed package inventory. Mise reuses installed
requested versions without forcing reinstalls. Existing native Herdr/Codex
binaries and Bob's Neovim installation are retained. Completed bootstrap stages
are skipped on resume.

The server's existing maintenance policy still upgrades outdated OS/AUR packages;
version declarations such as `latest` may also require a newer tool version.
Skipping reinstalls does not freeze package versions.

### Resume and boundaries

If a stage fails, fix its reported error and rerun:

```bash
chezmoi init --apply
```

Completed package/tool stages are recorded under
`~/.local/state/chezmoi/server-bootstrap/` (or `$XDG_STATE_HOME/chezmoi/server-bootstrap/`).
A `prepared` marker means the pre-apply stages succeeded; `complete` is written
only after the full apply reaches its final service checks. Reinitializing a
completed bootstrap skips provisioning. Ordinary status/diff commands and init
dry runs never provision through the bootstrap hook.

The `server` profile shares [OS package declarations](packages/README.md) with
dlco, including the ZFS/NVIDIA stack. Bootstrap postpones undeclared-package
pruning and package publication/convergence until the full apply. The full apply
activates those shared policies; this is not a minimal generic Arch profile.
The ZFS module requires booting `linux-lts`; select that in the machine's
bootloader before a planned reboot. Disk layouts, bootloader entries, network
identity, application data, and hostname-gated production services are not cloned
from dlco. Existing dotfiles should be backed up before enrolling an established
account.

Bootstrap uses the official [chezmoi init](https://www.chezmoi.io/reference/commands/init/)
and [hooks](https://www.chezmoi.io/reference/configuration-file/hooks/) interfaces,
[Tailscale Linux setup](https://tailscale.com/docs/install/linux),
[Taildrop](https://tailscale.com/docs/features/taildrop),
[mise install](https://mise.jdx.dev/cli/install.html), and the vendor
[Herdr](https://herdr.dev/install.sh) and
[Codex](https://learn.chatgpt.com/docs/codex/cli) installers.

## Safe daily use

```bash
chezmoi status
chezmoi diff
chezmoi apply --dry-run -v
chezmoi apply
```

`ce <target>` is the shell alias for `chezmoi edit --apply <target>`.
Chezmoi auto-commits and pushes source changes made through its commands. Plain
editor writes remain dirty until committed deliberately; package reconciliation
does not generate commits. The separate server package publisher does.

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
