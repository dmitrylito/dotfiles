# Package inventory

Package deployment runs from a chezmoi `run_onchange` hook when the active
machine's actionable inputs change. A no-op apply does not rerun Ansible. Run
`scripts/reconcile-packages.sh` explicitly for an audit; on Linux, use `--check`
first when package state has changed substantially.

## Ownership

- `omarchy/<hostname>/added-pacman.txt`: native packages intentionally added on
  that host.
- `omarchy/<hostname>/added-aur.txt`: AUR packages intentionally added there.
- `omarchy/<hostname>/removed.txt`: the only automatic removal list.
- `omarchy/<hostname>/{base,other}.packages`: snapshots of Omarchy-owned
  packages; reference only.
- `omarchy/<hostname>/drivers.txt`: hardware-specific reference; never
  installed automatically.
- `server/{pacman,aur}.txt`: canonical explicit package set shared by all
  server-profile Arch machines.
- `mac/{brew,casks,taps}.txt`: desired Homebrew set.

The old `untracked.regex` files are unnecessary. Omarchy does not prune by
absence. Server pruning is constrained to the shared declarations plus the ZFS
packages provisioned separately by the playbook; required undeclared packages
are retained and marked as dependencies.

## Regeneration

- Run `scripts/update_package_lists.sh` on an Omarchy host.
- Run `scripts/update_server_package_lists.sh` manually for an audit; the server
  Pacman hook normally schedules it after a successful transaction.
- Review the diff before committing; generation is not package policy.
- Do not hand-edit Omarchy base/other snapshots.

On server profiles, successful manual Pacman/yay transactions schedule a
debounced user service. It regenerates only `packages/server/`, commits those two
files, and pushes them. A pending marker makes its timer retry failures; a
reconciliation marker prevents feedback loops. Omarchy transactions never
mutate the dotfiles repository.

## Deliberate exclusions

- tmux and sesh are retired. Omarchy still ships tmux in its base snapshot, so
  `removed.txt` overrides it on each known host.
- Herdr is the supported multiplexer; its package/vendor installer owns it.
- `claude`, `codex`, GitHub CLI, Hey, Grok, Pi, Node, and similar npm tools
  belong to the managed mise configuration, not duplicate distro packages.
- `zsh-sage` and the other shell plugins are cloned by `playbook.yml`;
  do not add duplicate distro packages.
- distro Neovim stays off the desired lists because Bob owns `nvim`.
- `stow` is obsolete; Chezmoi owns dotfiles.
- GPU stacks remain in `drivers.txt` because they are host-specific and large.

## Reconciliation guarantees

The playbook installs missing declarations everywhere. Omarchy removes only
explicit `removed.txt` entries and never infers deletion from absence. Server
profiles repeatedly remove undeclared explicit leaves, then mark any remaining
undeclared hard dependencies non-explicit so both servers converge without
breaking dependency chains. Neither profile sweeps unrelated orphans, and
`drivers.txt` is never installed. During an AUR build, the temporary sudoers
entry permits only `/usr/bin/pacman *` and is removed in an `always` block.
