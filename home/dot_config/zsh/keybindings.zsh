# Carapace owns Tab completion. FZF's alternative Tab widget triggers a Sage
# wrapper bug (`_sage_orig_fzf-completion`), so restore Zsh's standard widget.
bindkey '^I' expand-or-complete

if (( ${+widgets[fzf-history-widget]} )); then
  bindkey '^[[A' fzf-history-widget
  bindkey '^[OA' fzf-history-widget
fi

# At a prompt, Ctrl-C clears the editor buffer. Restore the terminal's normal
# SIGINT character immediately before executing a command.
_ctrl_c_clear_input() {
  BUFFER=''
  CURSOR=0
  REGION_ACTIVE=0
  zle redisplay
}
zle -N _ctrl_c_clear_input
bindkey -M emacs '^C' _ctrl_c_clear_input
bindkey -M viins '^C' _ctrl_c_clear_input
bindkey -M vicmd '^C' _ctrl_c_clear_input

_ctrl_c_set_interrupt() {
  [[ -t 0 ]] || return
  (( ${+commands[stty]} )) || return
  command stty intr "$1" </dev/tty 2>/dev/null || true
}
_ctrl_c_before_prompt() {
  _ctrl_c_set_interrupt '^-'
}
_ctrl_c_restore_interrupt() {
  _ctrl_c_set_interrupt '^C'
}

add-zsh-hook precmd _ctrl_c_before_prompt
add-zsh-hook preexec _ctrl_c_restore_interrupt
add-zsh-hook zshexit _ctrl_c_restore_interrupt
