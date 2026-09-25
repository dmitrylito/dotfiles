# Repository agent guide

This is the canonical guide for agents working on this Chezmoi source repository.

## What this repository is

This is the **chezmoi source directory** (`~/.local/share/chezmoi`) — the Git-backed source of truth for Dmitry's dotfiles across three machine profiles: **omarchy** (Arch/Hyprland desktop), **mac**, and **server**. `scripts/test-templates.sh` validates isolated renders; deploying uses chezmoi.

`AGENTS.md.tmpl` renders per profile to `~/AGENTS.md`, the home-directory agent guide; `~/CLAUDE.md` and `~/GEMINI.md` are symlinks to it (`symlink_CLAUDE.md`, `symlink_GEMINI.md`). This file covers working *on the source repo itself*. It lives at `.claude/AGENTS.md` to avoid colliding with that deployed guide; chezmoi ignores dot-prefixed source directories. The home guide and README link here; `.claude/CLAUDE.md` is only a tool entry point.

## Critical mechanics

- **Files here are templates/sources, not the live files.** A source file named `dot_zshrc.tmpl` becomes `~/.zshrc`. Editing a source file does nothing until you `chezmoi apply`.
- **`autoCommit` and `autoPush` are enabled** (`.chezmoi.toml.tmpl`) for source changes made through chezmoi commands. Plain editor writes are not covered; validate them, then commit and push only when authorized. Package reconciliation does not publish; the separate server package-capture workflow does.
- **Source naming conventions** (chezmoi): `dot_` → leading `.`; `.tmpl` → rendered as a Go template; `executable_` → `+x`; `run_onchange_` → a script chezmoi executes (not deployed as a file) whenever its rendered content changes; `modify_` → a script chezmoi runs with the current target on stdin, whose stdout becomes the target.
- **`~/.claude/settings.json` is a `modify_` script, not a tracked file** (`dot_claude/modify_settings.json.tmpl`). Claude Code rewrites that file at runtime (`/model`, `/config`, `/plugin`) and `moshi-hook service install` rewrites its whole hooks block, so tracking it as a file meant permanent drift, an overwrite prompt on every apply, and lost settings. The script merges instead: baseline keys are defaults (`model` is seed-only on purpose), the moshi guard hook wiring is enforced. Do not convert it back to a plain file. `--exclude scripts` does **not** skip `modify_` entries, so `chezmoi-autoupdate` still repairs the wiring.
- **Secrets live in one file: `.secrets.yaml.age`** (age-encrypted YAML, dot-prefixed so it never deploys). Each top-level group renders to one env file through `.chezmoitemplates/secrets-env`: `shared` → `~/.config/secrets/shared.env` (sourced by every zsh, so keep it to keys every shell needs), `omada-mcp` → `~/.config/secrets/omada-mcp.env`, `caddy` → `~/.config/secrets/caddy.env` (servers only), `gluetun` → the Podman env file. Edit with `secrets-edit` (decrypts to tmpfs, validates, commits, pushes and applies). A new group needs a `private_<name>.env.tmpl` calling the template and a matching group in `scripts/test-templates.py`. Whole encrypted config files (homepage `services.yaml`, the Codex baseline, the Moshi token) stay separate `.age` files.
- **`~/.codex/config.toml` is also a `modify_` target** (`dot_codex/modify_private_config.toml.tmpl`). Codex writes project trust, hook hashes, and desktop state into this file at runtime. The encrypted seed lives at `scripts/codex-config-baseline.toml.age`; the modifier fills missing baseline keys while preserving existing live values, except for paths listed in `SYNCHRONIZED_SETTINGS`, including the shared status line. Update the baseline to change the shared statusline; do not capture routine runtime churn. The modifier uses `uv` with pinned `tomlkit` so synchronization does not depend on the active Python's packages. An uncached dependency needs network access on first use; dependency failures fail apply rather than silently preserving stale settings.
- **Three files feed Claude Code's config, each via its own `modify_` script.** `dot_claude/modify_settings.json.tmpl` → `~/.claude/settings.json`; `dot_claude/modify_settings.local.json.tmpl` → `~/.claude/settings.local.json`; `modify_private_dot_claude.json.tmpl` → `~/.claude.json` (90KB of per-machine state — machineID, userID, per-project history — so only enforced keys are touched and it writes with no trailing newline and `ensure_ascii=False` to avoid rewriting the whole file every apply). Settings that must be identical everywhere go in `ENFORCED_SCALARS`, not `BASELINE`: `BASELINE` only fills keys the live file lacks, so a box that already wrote the key keeps its old value forever. `outputStyle` is enforced in settings.json **and** stripped from settings.local.json, because `/config` writes it to the Local tier, which outranks User.
- **The active profile and role** are chosen at `chezmoi init`: `.profile` is `omarchy`, `server`, or `mac`; `.work` gates Fleet Chaser tooling independently of platform. Templates and `.chezmoiignore` must respect both dimensions.

## Common commands

```bash
scripts/test-templates.sh     # isolated renders and syntax checks; no deployment hooks
chezmoi apply                 # deploy to $HOME; changed hooks can reconcile packages
chezmoi apply --dry-run -v    # preview as a diff without touching $HOME — always do this first
chezmoi diff                  # show pending changes
chezmoi managed               # list every target path chezmoi controls
chezmoi status                # unapplied local changes
chezmoi execute-template < file.tmpl   # test that a .tmpl renders (e.g. .chezmoiignore, run_onchange script)
ce <file>                     # alias: chezmoi edit --apply <file> (edit source, deploy on save)
```

After moving/renaming source files, verify with `chezmoi execute-template` (templates) and `chezmoi managed | grep ...` (deployment), and preview only intended targets with `chezmoi apply --dry-run`. Preserve unrelated live drift. See `docs/validation.md` for validation prerequisites and limits.

## Deployment gating (`.chezmoiignore`)

`.chezmoiignore` is itself a template and uses **target ($HOME) paths**, not source paths. It does two jobs:
1. **Per-profile config gating** — e.g. `.config/hypr/` only deploys on omarchy; `.config/aerospace/`, `.config/sketchybar/` only on mac. If you add a profile-specific config, gate it here or it deploys everywhere.
2. **Keeping repo tooling out of `$HOME`** — `packages/`, `scripts/`, `docs/`, `playbook.yml`, `package-lock.json`, and `README.md` live in the repo but must never be deployed. `AGENTS.md` is intentionally *not* ignored (it deploys as the global agent guide).

When adding a new top-level tooling file or directory, add it to `.chezmoiignore` or it will land in `$HOME`.

Hyprland's `hyprland.lua` is a special ownership boundary: `dot_config/hypr/modify_hyprland.lua`
reads Omarchy's currently installed entrypoint and injects `require("hypr.chezmoi")` after
the standard toggles. Keep custom post-default behavior in `dot_config/hypr/chezmoi.lua`;
do not copy Omarchy's entrypoint back into the repository.

## Package management architecture

Package reconciliation is automatic when its active inputs change and remains
available as an explicit command:

- **`run_onchange_executable_reconcile-packages.sh.tmpl`** hashes the playbook, reconciliation script, profile/role, and only the active machine's actionable lists. It bootstraps Ansible when needed, then runs after `chezmoi init` or `apply`; unchanged applies are no-ops.
- **`scripts/reconcile-packages.sh`** is the shared entry point used by the hook and manual audits. It reads the current profile/role and runs the Ansible playbook; Linux uses sudo, macOS does not. Always use `--check` before a manual real run when lists changed substantially.
- **`playbook.yml`** installs declared packages. Omarchy removes only names explicitly present in the host's `removed.txt`; server profiles additionally prune undeclared explicit packages and demote undeclared packages that must remain as dependencies. The AUR block's temporary sudoers rule is restricted to `/usr/bin/pacman *` and removed in `always`.
- **`packages/omarchy/<hostname>/`** contains host-specific desired additions, explicit removals, and reference snapshots. `base.packages`, `other.packages`, and `drivers.txt` are never installed. There is no `untracked.regex` because there is no automatic prune.
- **`packages/server/`** and **`packages/mac/`** hold the corresponding desired sets.
- **`scripts/update_package_lists.sh`** regenerates Omarchy inventories manually. **`scripts/update_server_package_lists.sh`** is also called by the guarded server Pacman publisher.

Server hosts install a debounced Pacman post-transaction publisher, a retry
timer, and a root-owned convergence timer. Publication only runs when the
Pacman hook creates a pending marker; reconciliation holds a suppression marker,
so its own transactions cannot rewrite policy. Omarchy retains no publisher.
If paths under `packages/` change, update the playbook, run-on-change hashes, and
generator scripts together. `packages/README.md` is the canonical ownership
summary.

## Shared global agent instructions

Universal policy lives in `.chezmoitemplates/agent-rules.md`; shared code style
lives in `.chezmoitemplates/agent-code-style.md`. Chezmoi renders these into
`~/.codex/AGENTS.md` and Claude's auto-loaded `~/.claude/rules/` files. Edit
the shared templates to update both tools, then preview/apply the affected
targets and verify content equality. Keep tool-specific memory, permission,
model, hook, and documentation-tool settings in their own adapters.

These are instruction policies, not a new job runner or enforcing hook.
Long-running tasks must implement the documented logs and completion markers.
Start fresh agent sessions after applying instruction changes.

References: [Codex instructions](https://developers.openai.com/codex/guides/agents-md),
[Claude global rules](https://code.claude.com/docs/en/memory),
and [chezmoi templates](https://www.chezmoi.io/user-guide/templating/).
