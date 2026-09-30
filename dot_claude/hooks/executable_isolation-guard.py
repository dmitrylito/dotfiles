#!/usr/bin/env python3
"""isolation-guard.py — keep concurrent Claude sessions out of each other's checkout.

Usage (wired into ~/.claude/settings.json by dot_claude/modify_settings.json.tmpl):
    SessionStart:                              isolation-guard.py notify
    PreToolUse, matcher Write|Edit|NotebookEdit: isolation-guard.py guard

Reads the hook JSON on stdin, asks `claude agents --json` which other live sessions share
this session's git repo, and if any do: `notify` injects a note advising EnterWorktree,
`guard` denies the write so the session has to isolate before it can touch the checkout.
`guard` judges the repo of the file being written, not the session cwd, so writes outside
any repo (job tmp, ~/.local/state, memory) or into a linked worktree always pass.

Fails open on every error — a broken guard must never block editing.

A repo containing .claude/no-isolation-guard is exempt, for repos that genuinely cannot work
from a worktree copy — the chezmoi source is one, since `chezmoi apply` only reads the real
source directory. Do not add it merely to silence the guard.

Preconditions: `claude` on PATH; git repo (no repo, no guard). Set ISOLATION_GUARD=0 to
turn it off for a session.
"""

import json
import os
import subprocess
import sys

TIMEOUT = 10


def allow():
    sys.exit(0)


def git(cwd, *args):
    try:
        done = subprocess.run(
            ["git", "-C", cwd, *args],
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def toplevel(cwd, cache={}):
    if cwd not in cache:
        found = git(cwd, "rev-parse", "--show-toplevel")
        cache[cwd] = os.path.realpath(found) if found else None
    return cache[cwd]


def in_linked_worktree(cwd):
    if "/.claude/worktrees/" in cwd:
        return True
    own, shared = git(cwd, "rev-parse", "--git-dir"), git(cwd, "rev-parse", "--git-common-dir")
    if not own or not shared:
        return False
    resolve = lambda p: os.path.realpath(p if os.path.isabs(p) else os.path.join(cwd, p))
    return resolve(own) != resolve(shared)


def existing_dir(path):
    path = os.path.dirname(os.path.abspath(path))
    while path != "/" and not os.path.isdir(path):
        path = os.path.dirname(path)
    return path


def repo_opts_out(repo):
    return os.path.exists(os.path.join(repo, ".claude", "no-isolation-guard"))


def peers(repo, my_session_id):
    try:
        done = subprocess.run(
            ["claude", "agents", "--json"],
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
        )
        sessions = json.loads(done.stdout)
    except (OSError, subprocess.SubprocessError, ValueError):
        return []
    if not isinstance(sessions, list):
        return []
    found = []
    for session in sessions:
        if not isinstance(session, dict):
            continue
        if session.get("sessionId") == my_session_id:
            continue
        if session.get("state") == "done":
            continue
        cwd = session.get("cwd")
        if not cwd or not os.path.isdir(cwd) or toplevel(cwd) != repo:
            continue
        found.append(session.get("name") or session.get("id") or "unnamed")
    return found


def describe(names):
    listed = ", ".join(names[:4]) + (", …" if len(names) > 4 else "")
    plural = "sessions are" if len(names) > 1 else "session is"
    return f"{len(names)} other Claude {plural} live in this repo ({listed})"


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "notify"
    if os.environ.get("ISOLATION_GUARD") == "0":
        allow()
    try:
        payload = json.load(sys.stdin)
    except (ValueError, OSError):
        payload = {}
    cwd = payload.get("cwd") or os.getcwd()
    tool_input = payload.get("tool_input") or {}
    target = tool_input.get("file_path") or tool_input.get("notebook_path")
    if mode == "guard" and target:
        cwd = existing_dir(os.path.join(cwd, os.path.expanduser(target)))
    elif in_linked_worktree(os.getcwd()):
        allow()
    if in_linked_worktree(cwd):
        allow()
    repo = toplevel(cwd)
    if not repo or repo_opts_out(repo):
        allow()
    names = peers(repo, payload.get("session_id"))
    if not names:
        allow()
    if mode == "guard":
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": (
                    f"{describe(names)}, so writing to {repo} would collide with them. "
                    "Call EnterWorktree to get an isolated copy, then retry this edit "
                    "against the worktree path. Editing the shared checkout anyway needs "
                    "the user to restart this session with ISOLATION_GUARD=0."
                ),
            }
        }))
    else:
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": (
                    f"{describe(names)}. Writes to {repo} are blocked until this session "
                    "calls EnterWorktree, so isolate before your first edit."
                ),
            }
        }))
    allow()


main()
