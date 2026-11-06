# Carapace needs compdef, so load it after Oh My Zsh. Environment variables must
# be set before the generated initialization snippet is sourced.
if (( ${+commands[carapace]} )); then
  export CARAPACE_BRIDGES='zsh,bash'
  source <(carapace _carapace)
fi

# Load presentation rules after Oh My Zsh so its defaults cannot overwrite
# them. Completion stays inside ZLE, which is compatible with Sage.
zstyle ':completion:*' menu select
zstyle ':completion:*' group-name ''
zstyle ':completion:*:descriptions' format '%F{cyan}── %d ──%f'
zstyle ':completion:*:messages' format '%F{yellow}%d%f'
zstyle ':completion:*:warnings' format '%F{red}No matches for: %d%f'
zstyle ':completion:*' list-separator '  '
zstyle ':completion:*' select-prompt '%SScrolling: %p%s'
zstyle ':completion:*' matcher-list 'm:{a-zA-Z}={A-Za-z}'
zstyle ':completion:*:git:*' group-order \
  'main commands' 'alias commands' 'external commands'
