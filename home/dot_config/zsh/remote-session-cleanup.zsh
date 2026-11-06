# Restore terminal modes after commands that can leave the terminal dirty:
# ssh/mosh-style sessions that drop, and TUIs stopped with Ctrl-Z or resumed
# with fg. A suspended claude/codex/nvim can leave kitty keyboard protocol,
# bracketed paste, focus events, mouse reporting or the alt screen enabled,
# and its terminal-query replies (DA1/DA2, OSC 10/11, DECRQM) then land in zle
# as literal text. The zle widgets below swallow such replies at the prompt.
_term_cleanup_mode=''
_term_cleanup_tty=''

_term_cleanup_preexec() {
  local -a words=(${(z)1})
  _term_cleanup_mode=''
  case $words[1] in
    ssh|autossh|mosh|et) _term_cleanup_mode=remote ;;
    tailscale) [[ $words[2] == ssh ]] && _term_cleanup_mode=remote ;;
    fg|bg|%*) _term_cleanup_mode=job ;;
  esac
  _term_cleanup_tty=''
  [[ $_term_cleanup_mode == remote ]] && _term_cleanup_tty=$(stty -g 2>/dev/null)
}

_term_cleanup_precmd() {
  local rc=$?
  (( rc >= 146 && rc <= 148 )) && _term_cleanup_mode=${_term_cleanup_mode:-job}
  [[ -n $_term_cleanup_mode ]] || return
  local mode=$_term_cleanup_mode
  _term_cleanup_mode=''
  [[ -t 0 && -t 1 ]] || return

  if [[ $mode == remote ]]; then
    if [[ -n $_term_cleanup_tty ]]; then
      stty "$_term_cleanup_tty" 2>/dev/null || stty sane 2>/dev/null
    else
      stty sane 2>/dev/null
    fi
  fi
  printf '\e[<u\e[=0;1u\e[>4;0m\e[?1049l\e[?1000l\e[?1002l\e[?1003l\e[?1004l\e[?1005l\e[?1006l\e[?1015l\e[?2004l\e[?1l\e>\e[?7h\e[?25h\e[0m'
  while read -r -s -k 1 -t 0 _ 2>/dev/null; do :; done
}

add-zsh-hook preexec _term_cleanup_preexec
add-zsh-hook precmd _term_cleanup_precmd

_term_swallow_csi() {
  local c
  while read -r -s -k 1 -t 0.1 c 2>/dev/null; do
    [[ $c == [@-~] ]] && break
  done
}
_term_swallow_osc() {
  local c prev=''
  while read -r -s -k 1 -t 0.1 c 2>/dev/null; do
    [[ $c == $'\a' || ( $prev == $'\e' && $c == '\\' ) ]] && break
    prev=$c
  done
}
_term_swallow_noop() { :; }
zle -N _term_swallow_csi
zle -N _term_swallow_osc
zle -N _term_swallow_noop
for _m in emacs viins vicmd; do
  bindkey -M $_m '^[[?' _term_swallow_csi
  bindkey -M $_m '^[[>' _term_swallow_csi
  bindkey -M $_m '^[]' _term_swallow_osc
  bindkey -M $_m '^[[I' _term_swallow_noop
  bindkey -M $_m '^[[O' _term_swallow_noop
done
unset _m
