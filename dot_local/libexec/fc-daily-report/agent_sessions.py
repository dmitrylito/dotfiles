"""Summarize Claude Code and Codex sessions active in a time window.

Usage: python3 agent_sessions.py --start ISO --end ISO [--prompt-chars N]
       ssh HOST python3 -I - --start ISO --end ISO < agent_sessions.py
Prints one JSON object: {host, sessions, errors}. Standard library only, so it
runs unchanged on any machine over SSH. Reads ~/.claude/projects/*/*.jsonl and
~/.codex/sessions/**/rollout-*.jsonl touched since --start; never writes.
Prompts are the human-typed turns (tool results, hook and AGENTS.md injections
are skipped); `active` merges every logged event closer than ACTIVE_GAP_SECONDS.
"""

import argparse
import json
import socket
import sys
from datetime import datetime
from pathlib import Path

ACTIVE_GAP_SECONDS = 120
CODEX_INJECTED_PREFIXES = (
    "# AGENTS.md instructions",
    "<environment_context>",
    "<user_instructions>",
    "<permissions",
    "<turn_aborted>",
    "<user_shell_command>",
)


def when(value):
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except (AttributeError, ValueError):
        return None


def records(path):
    with path.open(errors="replace") as handle:
        for line in handle:
            try:
                yield json.loads(line)
            except ValueError:
                continue


def intervals(times):
    merged = []
    for moment in sorted(times):
        if merged and moment - merged[-1][1] <= ACTIVE_GAP_SECONDS:
            merged[-1][1] = moment
        else:
            merged.append([moment, moment])
    return merged


def text_of(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict)
            and block.get("type") in {"text", "input_text"}
        )
    return ""


def claude_prompt(record):
    if record.get("type") != "user" or record.get("isSidechain"):
        return None
    if record.get("isMeta"):
        return None
    content = (record.get("message") or {}).get("content")
    if isinstance(content, list) and any(
        isinstance(block, dict) and block.get("type") == "tool_result"
        for block in content
    ):
        return None
    origin = record.get("origin")
    if isinstance(origin, dict) and origin.get("kind") != "human":
        return None
    text = text_of(content).strip()
    if not text or text.startswith("<"):
        return None
    return text


def claude_sessions(start, end, prompt_chars):
    root = Path.home() / ".claude/projects"
    for path in root.glob("*/*.jsonl"):
        if path.stat().st_mtime < start:
            continue
        session = {
            "agent": "claude",
            "session_id": path.stem,
            "project_dir": path.parent.name,
            "title": None,
            "cwd": None,
            "branch": None,
            "prompts": [],
        }
        times = []
        for record in records(path):
            if record.get("type") == "ai-title":
                session["title"] = record.get("aiTitle") or session["title"]
            elif record.get("type") == "custom-title":
                session["title"] = record.get("customTitle") or session["title"]
            moment = when(record.get("timestamp"))
            if moment is None or not start <= moment < end:
                continue
            times.append(moment)
            session["cwd"] = record.get("cwd") or session["cwd"]
            session["branch"] = record.get("gitBranch") or session["branch"]
            if (text := claude_prompt(record)) is not None:
                session["prompts"].append(
                    {"at": moment, "text": text[:prompt_chars]}
                )
        if times:
            yield session | {"active": intervals(times)}


def codex_titles():
    titles = {}
    index = Path.home() / ".codex/session_index.jsonl"
    if index.exists():
        for record in records(index):
            if record.get("id") and record.get("thread_name"):
                titles[record["id"]] = record["thread_name"]
    return titles


def codex_sessions(start, end, prompt_chars):
    root = Path.home() / ".codex/sessions"
    titles = codex_titles()
    for path in root.glob("*/*/*/rollout-*.jsonl"):
        if path.stat().st_mtime < start:
            continue
        session = {
            "agent": "codex",
            "session_id": None,
            "title": None,
            "cwd": None,
            "branch": None,
            "repository": None,
            "prompts": [],
        }
        times = []
        for record in records(path):
            payload = record.get("payload")
            payload = payload if isinstance(payload, dict) else {}
            if record.get("type") == "session_meta":
                git = payload.get("git") or {}
                session.update(
                    session_id=payload.get("id"),
                    cwd=payload.get("cwd"),
                    branch=git.get("branch"),
                    repository=git.get("repository_url"),
                )
                continue
            moment = when(record.get("timestamp"))
            if moment is None or not start <= moment < end:
                continue
            times.append(moment)
            if record.get("type") == "turn_context":
                session["cwd"] = payload.get("cwd") or session["cwd"]
            if (
                record.get("type") == "response_item"
                and payload.get("type") == "message"
                and payload.get("role") == "user"
            ):
                text = text_of(payload.get("content")).strip()
                if text and not text.startswith(CODEX_INJECTED_PREFIXES):
                    session["prompts"].append(
                        {"at": moment, "text": text[:prompt_chars]}
                    )
        if times:
            session["title"] = titles.get(session["session_id"])
            yield session | {"active": intervals(times)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--prompt-chars", type=int, default=300)
    args = parser.parse_args()
    start, end = when(args.start), when(args.end)
    host = socket.gethostname()
    sessions, errors = [], []
    for reader in (claude_sessions, codex_sessions):
        try:
            for session in reader(start, end, args.prompt_chars):
                sessions.append(session | {"host": host})
        except OSError as exc:
            errors.append(f"{reader.__name__}: {exc}")
    json.dump(
        {"host": host, "sessions": sessions, "errors": errors}, sys.stdout
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
