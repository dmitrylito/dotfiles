# Package inventory

Package deployment runs from a chezmoi `run_onchange` hook when the active
machine's actionable inputs change. A no-op apply does not rerun Ansible. Run
`scripts/reconcile-packages.sh` explicitly for an audit; on Linux, use `--check`
first when package state has changed substantially.

Fresh server initialization uses `scripts/bootstrap-server.sh` before encrypted
files are read. It passes `server_bootstrap=true` to install the declared packages
while deferring package pruning and synchronization setup. The normal full apply
then runs reconciliation with its existing defaults. See the root README for the
single-command setup flow.

## Ownership

- `omarchy/common/{pacman,aur}.txt`: installed on every Omarchy host.
- `omarchy/<hostname>/{pacman,aur}.txt`: installed on that host too (hardware,
  GPU stacks, role-specific tools).
- `omarchy/removed.txt`: uninstalled on every Omarchy host and never installed.
- `omarchy/<hostname>/removed.txt`: the same for one host; also keeps a
  `common/` entry off that host.
- `omarchy/<hostname>/ignored.txt`: installed there but deliberately untracked;
  the review never asks about them.
- Omarchy's own defaults are read live from `/usr/share/omarchy/install/` and
  are never listed here.
- `server/{pacman,aur}.txt`: canonical explicit package set shared by all
  server-profile Arch machines.
- `server/hosts/<hostname>/added-pacman.txt`: native packages kept only on
  that server; capture excludes them from the shared list.
- `server/hosts/<hostname>/added-aur.txt`: AUR packages kept only on that
  server; capture excludes them from the shared list.
- `server/hosts/<hostname>/excluded-pacman.txt`: shared native packages not
  installed on that server; capture retains them in the shared list.
- `mac/{brew,casks,taps}.txt`: desired Homebrew set.

Server hosts are identical apart from CPU and role: DLCO-1 alone declares ZFS
(`zfs-linux-lts`, `zfs-utils` in its added list turn on the archzfs stack),
ollama and samba; DLCO-2 adds libvirt; DLCO-3 swaps in `amd-ucode` and drops
the NVIDIA stack. Every server boots Limine into the linux-lts UKI
(`scripts/server-limine.sh`, installed as `chezmoi-limine-sync`).

Omarchy does not prune by absence. Server pruning is constrained to the shared and per-host declarations;
required undeclared packages are retained and marked as dependencies, and
makepkg `-debug` companions (now disabled in `/etc/makepkg.conf`) are removed.

## Regeneration

- Omarchy lists are edited by hand or through `scripts/update_package_lists.sh`,
  which `czu` runs between pulling and applying when there is a TTY. It offers
  explicit packages nothing depends on that are undeclared (install on all hosts,
  this host, or ignore) and declared packages removed on this host (remove on all
  hosts, this host, or reinstall), then commits and pushes the list changes.
- Run `scripts/update_server_package_lists.sh` manually for an audit; the server
  Pacman hook normally schedules it after a successful transaction.
- Review the diff before committing; generation is not package policy.

On server profiles, successful manual Pacman/yay transactions schedule a
debounced user service. It regenerates only `packages/server/`, commits those two
files, and pushes them. A pending marker makes its timer retry failures; a
reconciliation marker prevents feedback loops. Omarchy transactions never
mutate the dotfiles repository.

## Deliberate exclusions

- tmux and sesh are retired. Omarchy still ships tmux, so `omarchy/removed.txt`
  overrides it.
- Herdr is the supported multiplexer; its package/vendor installer owns it.
- `claude`, `codex`, GitHub CLI, Hey, Grok, Pi, Node, and similar npm tools
  belong to the managed mise configuration, not duplicate distro packages.
- `zsh-sage` and the other shell plugins are cloned by `playbook.yml`;
  do not add duplicate distro packages.
- distro Neovim stays off the desired lists because Bob owns `nvim`.
- `stow` is obsolete; Chezmoi owns dotfiles.
- GPU stacks go in the host's lists, never `common/`, because they are
  hardware-specific and large.

## Reconciliation guarantees

The playbook installs missing declarations everywhere. Omarchy removes only
explicit `removed.txt` entries and never infers deletion from absence; it also
skips any declared package whose last `pacman.log` event is a removal, so an
apply never undoes a local removal before the review records a decision. Server
profiles repeatedly remove undeclared explicit leaves, then mark any remaining
undeclared hard dependencies non-explicit so both servers converge without
breaking dependency chains. Neither profile sweeps unrelated orphans. During an AUR build, the temporary sudoers
entry permits only `/usr/bin/pacman *` and is removed in an `always` block.
