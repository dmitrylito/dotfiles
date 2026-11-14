#!/bin/sh
# program-status.sh — report a background Claude session's state as OSC 7501.
#
# Usage: hook command `sh ~/.claude/hooks/program-status.sh <state> [kind]`, wired per event
#        by dot_claude/modify_settings.json.tmpl. <state> is idle|working|done|blocked|error|clear,
#        [kind] (blocked only) is permission|question.
#
# Why: sessions run by the Claude daemon (CLAUDE_CODE_SESSION_KIND=bg) never send OSC 7501
# themselves — Claude Code settles that capability to "no" for bg workers — so herdr-core
# terminals attached to them (herdr desktop app agents view) show no agent. Bytes written to
# the worker's pty pass through bg-pty-host and `claude attach` to the viewing terminal.
# terminalSequence can't carry this: its allowlist excludes OSC 7501.
#
# Foreground sessions are skipped: they send OSC 7501 on their own when the terminal answers
# the probe. Silent and always exits 0. Linux reads /proc; macOS has none, so it asks ps.

cat >/dev/null 2>&1

state=$1
kind=${2-}
case $state in idle | working | done | blocked | error | clear) ;; *) exit 0 ;; esac

if [ -d /proc/self ]; then
  is_bg() { grep -qzx 'CLAUDE_CODE_SESSION_KIND=bg' "/proc/$1/environ" 2>/dev/null; }
  tty_of() { readlink "/proc/$1/fd/1" 2>/dev/null; }
  parent_of() { awk '/^PPid:/ {print $2}' "/proc/$1/status" 2>/dev/null; }
else
  is_bg() { ps eww -o command= -p "$1" 2>/dev/null | grep -q 'CLAUDE_CODE_SESSION_KIND=bg\( \|$\)'; }
  tty_of() { t=$(ps -o tty= -p "$1" 2>/dev/null | tr -d ' '); case $t in ttys*) echo "/dev/$t" ;; esac; }
  parent_of() { ps -o ppid= -p "$1" 2>/dev/null | tr -d ' '; }
fi

if [ -n "${XDG_RUNTIME_DIR-}" ]; then
  dir=$XDG_RUNTIME_DIR/claude-bg-status
elif [ -d "/run/user/$(id -u)" ]; then
  dir=/run/user/$(id -u)/claude-bg-status
else
  dir=$HOME/.cache/claude-bg-status
fi

pid=$PPID
depth=0
while [ "$depth" -lt 6 ] && [ "${pid:-0}" -gt 1 ]; do
  if is_bg "$pid"; then
    tty=$(tty_of "$pid")
    case $tty in /dev/pts/* | /dev/ttys*) ;; *) exit 0 ;; esac
    fields="state=$state:app=claude-code"
    [ "$state" = blocked ] && [ -n "$kind" ] && fields="$fields:kind=$kind"
    printf '\033]7501;%s\033\\' "$fields" >"$tty" 2>/dev/null
    # herdr-bg-status-replay re-sends this when a viewer attaches; hooks only fire on events.
    file="$dir/$(echo "${tty#/dev/}" | tr / -)"
    if [ "$state" = clear ]; then
      rm -f "$file"
    else
      mkdir -p "$dir" && printf '%s' "$fields" >"$file.tmp" && mv -f "$file.tmp" "$file"
    fi 2>/dev/null
    exit 0
  fi
  pid=$(parent_of "$pid")
  depth=$((depth + 1))
done
exit 0
