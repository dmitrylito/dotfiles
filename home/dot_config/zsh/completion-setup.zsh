# Prepare completion paths before Oh My Zsh runs compinit.
ZCOMPDUMP_DIR="$XDG_CACHE_HOME/zsh"
mkdir -p "$ZCOMPDUMP_DIR" "$HOME/.zsh/completions" \
  "$HOME/.local/share/zsh/site-functions"
export ZSH_COMPDUMP="$ZCOMPDUMP_DIR/.zcompdump-${HOST:-local}-${ZSH_VERSION}"

fpath=(
  "$HOME/.zsh/completions"
  "$HOME/.local/share/zsh/site-functions"
  /usr/local/share/zsh/site-functions
  /usr/share/zsh/site-functions
  /opt/homebrew/share/zsh/site-functions
  $fpath
)

# Cache completions for CLIs that generate, but do not install, a Zsh function.
cache_zsh_completion() {
  setopt localoptions pipefail
  local name=$1 executable=$2
  shift 2
  [[ -x $executable ]] || return

  local completion="$HOME/.local/share/zsh/site-functions/_$name"
  [[ -s $completion && $completion -nt $executable ]] && return

  local tmp="$completion.$$"
  if "$executable" "$@" 2>/dev/null |
      awk 'seen || /^#compdef / { seen=1; print }' >| "$tmp" && [[ -s $tmp ]]; then
    mv -f -- "$tmp" "$completion"
  else
    rm -f -- "$tmp"
  fi
}

# Carapace owns commands covered by its specs, so cache only local exceptions.
cache_zsh_completion codex "$XDG_DATA_HOME/mise/installs/codex/latest/bin/codex" completion zsh
cache_zsh_completion herdr "$commands[herdr]" completion zsh
unfunction cache_zsh_completion
