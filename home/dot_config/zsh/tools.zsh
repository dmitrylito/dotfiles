# Optional interactive tool integrations. Every integration is independently
# guarded so one missing package cannot break shell startup on another machine.
if (( ${+commands[zoxide]} )); then
  eval "$(zoxide init --cmd cd zsh)"
  cd() {
    builtin cd "$@" 2>/dev/null || __zoxide_z "$@"
  }
fi

(( ${+commands[mise]} )) && eval "$(mise activate zsh)"
(( ${+commands[direnv]} )) && eval "$(direnv hook zsh)"

# iTerm2 only installs this file on macOS; its prompt hooks are dead weight elsewhere.
[[ $TERM_PROGRAM == iTerm.app ]] && source_if_exists "$HOME/.iterm2_shell_integration.zsh"
