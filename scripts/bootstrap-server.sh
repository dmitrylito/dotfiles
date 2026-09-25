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

if [[ $mode == finish ]]; then
  sudo chsh -s /usr/bin/zsh "$(id -un)"
  systemctl is-active --quiet sshd.service tailscaled.service chezmoi-server-package-converge.timer
  systemctl --user is-active --quiet chezmoi-package-capture.timer moshi-hook.service
  printf 'complete\n' > "$state_dir/complete"
  printf '\nServer setup complete. Log out and back in for Zsh and the cz alias.\n'
  printf 'Sign in to Claude/Codex when first using them; boot linux-lts for the ZFS module.\n'
  exit 0
fi

[[ $(cz execute-template '{{ .profile | lower }}') == server ]]
if [[ -f $state_dir/prepared ]]; then
  cz decrypt "$source_dir/scripts/codex-config-baseline.toml.age" >/dev/null
  exit 0
fi

printf '\nInstalling bootstrap dependencies and enabling SSH/Tailscale...\n'
sudo pacman -Syu --needed --noconfirm git openssh curl jq python python-uv ansible tailscale dbus rsync
sudo systemctl enable --now sshd.service tailscaled.service
sudo loginctl enable-linger "$(id -un)"
sudo systemctl start "user@$(id -u).service"
sudo tailscale up --ssh --timeout=15m
tailscale status

if [[ ! -f $state_dir/packages-installed ]]; then
  "$source_dir/scripts/reconcile-packages.sh" --extra-vars '{"server_bootstrap":true}'
  printf 'installed\n' > "$state_dir/packages-installed"
fi

if [[ ! -f $state_dir/tools-installed ]]; then
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

printf '\nConfiguring GitHub access for automatic dotfile/package synchronization...\n'
if ! mise -C "$state_dir/tools" exec -- gh auth status --hostname github.com >/dev/null 2>&1; then
  mise -C "$state_dir/tools" exec -- gh auth login --hostname github.com --git-protocol https --web
fi
mise -C "$state_dir/tools" exec -- gh auth setup-git --hostname github.com
if ! git -C "$source_dir" config user.name >/dev/null; then
  git -C "$source_dir" config user.name "$(mise -C "$state_dir/tools" exec -- gh api user --jq '.name // .login')"
fi
if ! git -C "$source_dir" config user.email >/dev/null; then
  git -C "$source_dir" config user.email "$(mise -C "$state_dir/tools" exec -- gh api user --jq '"\(.id)+\(.login)@users.noreply.github.com"')"
fi

if [[ ! -s $key_file ]]; then
  mkdir -p "$state_dir/inbox"
  printf '\nTooling and networking are ready. Send the existing age key from DLCO-1:\n'
  printf '  rsync --protect-args --chmod=F600 -e ssh -- ~/.config/chezmoi/key.txt %q\n' "$(id -un)@$(tailscale ip -4):$state_dir/inbox/key.txt"
  printf 'Your tailnet policy must allow SSH from DLCO-1 to this tagged machine as %s.\n' "$(id -un)"
  printf 'You can also transfer the key to %s through an existing SSH login.\n' "$key_file"
  read -r -p 'Press Enter after sending the key: ' </dev/tty
  if [[ ! -s $key_file ]]; then
    [[ -s $state_dir/inbox/key.txt ]] || { printf 'No key.txt received; rerun chezmoi init --apply after transferring it with rsync.\n' >&2; exit 1; }
    install -d -m 700 "$(dirname "$key_file")"
    sudo install -o "$(id -u)" -g "$(id -g)" -m 600 "$state_dir/inbox/key.txt" "$key_file"
    sudo rm -- "$state_dir/inbox/key.txt"
  fi
fi
cz decrypt "$source_dir/scripts/codex-config-baseline.toml.age" >/dev/null
printf 'prepared\n' > "$state_dir/prepared"
printf '\nEncryption verified. Continuing with your managed configuration and services...\n'
