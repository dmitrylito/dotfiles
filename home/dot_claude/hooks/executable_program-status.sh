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
# the probe. Silent and always exits 0; on a box without /proc it does nothing.

cat >/dev/null 2>&1

state=$1
kind=${2-}
case $state in idle | working | done | blocked | error | clear) ;; *) exit 0 ;; esac

pid=$PPID
depth=0
while [ "$depth" -lt 6 ] && [ "${pid:-0}" -gt 1 ]; do
  if grep -qzx 'CLAUDE_CODE_SESSION_KIND=bg' "/proc/$pid/environ" 2>/dev/null; then
    tty=$(readlink "/proc/$pid/fd/1" 2>/dev/null)
    case $tty in /dev/pts/*) ;; *) exit 0 ;; esac
    fields="state=$state:app=claude-code"
    [ "$state" = blocked ] && [ -n "$kind" ] && fields="$fields:kind=$kind"
    printf '\033]7501;%s\033\\' "$fields" >"$tty" 2>/dev/null
    exit 0
  fi
  pid=$(awk '/^PPid:/ {print $2}' "/proc/$pid/status" 2>/dev/null)
  depth=$((depth + 1))
done
exit 0
