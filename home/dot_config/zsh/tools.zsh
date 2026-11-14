# Optional interactive tool integrations. Every integration is independently
# guarded so one missing package cannot break shell startup on another machine.
if source_cached_init zoxide zoxide init --cmd cd zsh; then
  cd() {
    builtin cd "$@" 2>/dev/null || __zoxide_z "$@"
  }
fi

(( ${+commands[mise]} )) && eval "$(mise activate zsh)"
source_cached_init direnv direnv hook zsh

# iTerm2 only installs this file on macOS; its prompt hooks are dead weight elsewhere.
[[ $TERM_PROGRAM == iTerm.app ]] && source_if_exists "$HOME/.iterm2_shell_integration.zsh"
