#!/usr/bin/env bash
# Bootstrap an Arch server through `chezmoi init --apply dmitrylito`.
# Called by the init source-read hook (prepare) and the after-apply script (finish).
# Requires internet and a non-root login with sudo. Prompts use the controlling TTY.
set -euo pipefail

mode=${1:-}
case "$mode" in
  prepare)
    [[ ${CHEZMOI_COMMAND:-} == init ]] || exit 0
    # Chezmoi runs config hooks even on dry runs; never provision from a preview.
    read -r -a chezmoi_args <<< "${CHEZMOI_ARGS:-}"
    for arg in "${chezmoi_args[@]}"; do
      if [[ $arg == --dry-run* || $arg =~ ^-[^-]*n ]]; then
        exit 0
      fi
    done
    ;;
  finish) ;;
  *) printf 'Use chezmoi init --apply to start or resume server setup.\n' >&2; exit 2 ;;
esac

source_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
state_dir="${XDG_STATE_HOME:-$HOME/.local/state}/chezmoi/server-bootstrap"
key_file="$HOME/.config/chezmoi/key.txt"
[[ ! -f $state_dir/complete ]] || exit 0
if [[ $mode == finish && ! -f $state_dir/prepared ]]; then
  exit 0
fi

if [[ $(id -u) == 0 ]] || ! command -v pacman >/dev/null 2>&1; then
  printf 'Server setup requires a normal Arch login user with sudo access.\n' >&2
  exit 1
fi
export PATH="$HOME/.local/bin:$HOME/.local/share/mise/shims:$PATH"
export XDG_RUNTIME_DIR="/run/user/$(id -u)"
export DBUS_SESSION_BUS_ADDRESS="unix:path=$XDG_RUNTIME_DIR/bus"
umask 077
mkdir -p "$state_dir"

cz() {
  "${CHEZMOI_EXECUTABLE:-chezmoi}" \
    --config "${CHEZMOI_CONFIG_FILE:-$HOME/.config/chezmoi/chezmoi.toml}" \
    --source "$source_dir" "$@"
}

select_step() {
  local choice
  while true; do
    printf '\n%s — [Enter] run / [s] skip / [q] quit: ' "$1" >&2
    IFS= read -r -s -n 1 choice </dev/tty
    printf '\n' >&2
    case "$choice" in
      '') return 0 ;;
      s|S) printf 'Skipped: %s\n' "$1"; return 1 ;;
      q|Q) printf 'Setup paused. Resume with chezmoi init --apply.\n'; exit 1 ;;
    esac
  done
}

if [[ $mode == finish ]]; then
  if select_step "Set Zsh as your login shell"; then
    sudo chsh -s /usr/bin/zsh "$(id -un)"
  fi
  systemctl is-active --quiet sshd.service tailscaled.service chezmoi-server-package-converge.timer
  systemctl --user is-active --quiet chezmoi-package-capture.timer moshi-hook.service
  printf 'complete\n' > "$state_dir/complete"
  printf '\nServer setup complete. Start a new Zsh session to load your aliases.\n'
  printf 'Sign in to Claude/Codex when first using them; boot linux-lts for the ZFS module.\n'
  exit 0
fi

[[ $(cz execute-template '{{ .profile | lower }}') == server ]]
if [[ -f $state_dir/prepared ]]; then
  cz decrypt "$source_dir/scripts/codex-config-baseline.toml.age" >/dev/null
  exit 0
fi

if select_step "Install bootstrap dependencies"; then
  sudo pacman -Syu --needed --noconfirm git openssh curl jq python python-uv ansible tailscale dbus rsync
fi
if select_step "Enable SSH and Tailscale networking"; then
  sudo systemctl enable --now sshd.service tailscaled.service
  sudo loginctl enable-linger "$(id -un)"
  sudo systemctl start "user@$(id -u).service"
  sudo tailscale up --ssh --timeout=15m
  tailscale status
fi

if [[ ! -f $state_dir/packages-installed ]] && select_step "Preinstall declared server packages"; then
  "$source_dir/scripts/reconcile-packages.sh" --extra-vars '{"server_bootstrap":true}'
  printf 'installed\n' > "$state_dir/packages-installed"
fi

if [[ ! -f $state_dir/tools-installed ]] && select_step "Install mise tools, Neovim, Herdr, and Codex"; then
  mkdir -p "$state_dir/tools"
  cz execute-template < "$source_dir/dot_config/mise/config.toml.tmpl" > "$state_dir/tools/mise.toml"
  mise -C "$state_dir/tools" trust "$state_dir/tools/mise.toml"
  mise -C "$state_dir/tools" install
  if [[ ! -x $HOME/.local/share/bob/nvim-bin/nvim ]]; then
    printf '{"add_neovim_binary_to_path":false}\n' > "$state_dir/bob.json"
    BOB_CONFIG="$state_dir/bob.json" bob use stable
  fi
  if [[ ! -x $HOME/.local/bin/herdr ]]; then
    curl -fsSL --retry 2 --connect-timeout 15 --max-time 120 https://herdr.dev/install.sh -o "$state_dir/herdr-install.sh"
    sh "$state_dir/herdr-install.sh"
  fi
  if [[ ! -x $HOME/.local/bin/codex ]]; then
    curl -fsSL --retry 2 --connect-timeout 15 --max-time 120 https://chatgpt.com/codex/install.sh -o "$state_dir/codex-install.sh"
    sh "$state_dir/codex-install.sh"
  fi
  herdr --version
  codex --version
  printf 'installed\n' > "$state_dir/tools-installed"
fi

if [[ ! -s $key_file ]] && select_step "Pull the age key from another machine"; then
  mkdir -p "$state_dir/inbox"
  read -r -p 'Key source SSH login [dmitrylito@DLCO-1]: ' key_source </dev/tty
  key_source=${key_source:-dmitrylito@DLCO-1}
  rsync --protect-args --perms --chmod=F600 -e ssh -- \
    "$key_source:.config/chezmoi/key.txt" "$state_dir/inbox/key.txt"
  [[ -s $state_dir/inbox/key.txt ]] || { printf 'The transfer did not provide key.txt.\n' >&2; exit 1; }
  install -d -m 700 "$(dirname "$key_file")"
  install -m 600 "$state_dir/inbox/key.txt" "$key_file"
  rm -- "$state_dir/inbox/key.txt"
fi
if [[ ! -s $key_file ]]; then
  printf 'No age key is installed. Tool setup is preserved; encrypted configuration is paused.\n' >&2
  printf 'Resume with chezmoi init --apply when ready to transfer the key.\n' >&2
  exit 1
fi
cz decrypt "$source_dir/scripts/codex-config-baseline.toml.age" >/dev/null
if ! select_step "Apply managed configuration and the normal package policy"; then
  printf 'Configuration apply paused. Resume with chezmoi init --apply.\n'
  exit 1
fi
printf 'prepared\n' > "$state_dir/prepared"
printf '\nEncryption verified. Continuing with your managed configuration and services...\n'
