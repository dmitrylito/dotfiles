# Template validation

Run `scripts/test-templates.sh` from any directory. Prerequisites on Linux or
macOS are Python 3.11+, chezmoi, uv, bash, zsh, and Lua's `luac` compiler on PATH.
The implementation was verified with chezmoi 2.72.2. The Codex modifier uses uv
to fetch pinned `tomlkit==0.13.3` into the disposable cache, so the run needs
package-index access. No personal age identity, configured Chezmoi home, Mise
environment, Omarchy installation, or running desktop is required.

The harness copies the current source, including uncommitted edits, into a
temporary directory. It generates a fresh age key and replaces an explicit
inventory of encrypted inputs with nonsecret test ciphertext there. Adding or
removing an encrypted source requires updating that inventory; real ciphertext
is never decrypted. Temporary homes, Chezmoi state, and uv cache are removed at
exit. Commands have a 120-second timeout and failure output is limited to the
last 8,000 stderr characters; commands are not retried.

Chezmoi `dump` computes target contents and executes `modify_` scripts without
applying files or running `run_` deployment hooks. Package reconciliation,
service changes, commits, and pushes are not part of validation. The production
modifiers are unchanged and still fail when required real inputs are missing.

Coverage includes:

- `omarchy`, `server`, and `mac`, each with `work=false` and `work=true`.
- `fcoffice` Omarchy and `DLCO-2` server, each with both work roles.
- Initialization-template TOML and rendered Bash/Zsh, Python, Lua, and TOML syntax.
- Modifier Python syntax, Claude settings JSON, profile tool ownership, Arch plugin
  gating, home-path rendering, production-service routing, and workstation GPU gating.

The `mac` cases override the template OS to Darwin; they still execute on the
host running the test. They do not prove macOS runtime behavior. Secret contents,
installed services, deployment hooks, and interactive desktop behavior remain
outside this test. Fixture-based Omarchy validation does not prove compatibility
with a changed upstream entrypoint.

On an Omarchy desktop, also run:

```bash
scripts/test-templates.sh --installed-omarchy
```

This additionally reads `${OMARCHY_PATH:-/usr/share/omarchy}/config/hypr/hyprland.lua`,
runs the actual entrypoint modifier, and checks the resulting Lua syntax. An
explicitly supplied missing path fails this optional check. Preview deployment
separately with `chezmoi apply --dry-run --verbose <intended-targets>`.

References: [Chezmoi dump](https://www.chezmoi.io/reference/commands/dump/),
[built-in age-keygen](https://www.chezmoi.io/reference/commands/age-keygen/),
and [template execution](https://www.chezmoi.io/reference/commands/execute-template/).

## Fresh-server bootstrap

Run `python3 scripts/test-server-bootstrap.py` to exercise the real chezmoi
`init --apply` lifecycle in disposable homes with generated age keys and mocked
package managers, vendor downloads, authentication, and systemd. It checks
keyless startup, deferred secret application, dry-run isolation, failure handling,
completion markers, and idempotent reinitialization. Requires chezmoi, Git,
Python 3.11+, and Linux PTYs. It does not validate actual Arch package installation
or boot/network service behavior; those still require a fresh-server run.
