#!/usr/bin/env python3
"""style-guard.py — enforces the output contract in style-rules.md on every response.

Wired from ~/.claude/settings.json (hook JSON arrives on stdin):
    style-guard.py inject      UserPromptSubmit -> short reminder of the contract
    style-guard.py observe     Stop             -> records only, NEVER writes output
    style-guard.py check       (unwired)        -> all checks, blocks on failure
    style-guard.py check-fast  (unwired)        -> word/preamble patterns only

NOTHING ON THE STOP PATH BLOCKS ANY MORE, by Dmitry's decision on 2026-08-19. A block cost
three transcript entries — the discarded response, the instruction, and the rewrite — all
re-sent on every later turn, with autoCompact off, and no hook output field can delete a
message once written. Warnings were no use to him either. So Stop runs `observe`: it records
what the contract would have caught and writes nothing at all. Enforcement is now purely
preventative, via the Terse output style, which carries style-rules.md in the system prompt.

`check` and `check-fast` keep the blocking behaviour and are left unwired, for testing and in
case he wants enforcement back. Re-enable by putting "Stop": ("check", 20) in STYLE_HOOKS in
dot_claude/modify_settings.json.tmpl.

There used to be a Haiku judge on this path. It cost ~10s on EVERY response and could only
warn, and its whole recorded catch was two things now checked directly and more accurately:
closing_recap() measures the padding it flagged, and ungrounded_paths() resolves asserted
paths against the filesystem and the transcript rather than guessing from a truncated
excerpt. Do not reintroduce an LLM here — a Stop hook is on the critical path of every turn.

Env:
    STYLE_GUARD=0        disable everything
    STYLE_GUARD_GROUNDING=0  keep the word checks, skip path verification

`inject` deliberately does NOT re-send style-rules.md: the Terse output style already
includes that same file, so the full text is in the system prompt and sending it again each
turn paid for the same tokens twice. What ships per turn is REMINDER — the failure modes the
verdict log actually shows — while `check` still judges against the full file.

Every checked response appends one line to $XDG_STATE_HOME/claude-style-guard/verdicts.jsonl
(outcome: clean / blocked / over-cap / ungrounded). The style-tuner skill mines that log to
propose contract edits; without it the only record is whatever leaked into a transcript.

Pure stdlib, no subprocesses, no network. Runs in ~20ms.
"""

import json
import os
import re
import sys
import time
from pathlib import Path

RULES_FILE = Path(__file__).resolve().with_name("style-rules.md")
MAX_BLOCKS_PER_TURN = 1
# A block costs the discarded response, the instruction, and the rewrite — all three stay in
# the transcript and are re-sent every later turn, and autoCompact is off. So only failures
# that make the answer structurally worse are worth one; a single wrong word is a warning.
STRUCTURAL = ("preamble:", "padding:", "markdown heading")
WORDS_BEFORE_BLOCK = 3
VERDICT_LOG = Path(
    os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state"
) / "claude-style-guard" / "verdicts.jsonl"

BANNED = [
    (r"\bleverag(e|es|ed|ing)\b", "leverage -> use"),
    (r"\butiliz(e|es|ed|ing|ation)\b", "utilize -> use"),
    (r"\bin order to\b", "in order to -> to"),
    (r"\bfacilitat(e|es|ed|ing)\b", "facilitate -> help"),
    (r"\b(essentially|basically|fundamentally)\b", "filler adverb"),
    (r"\b(it'?s|it is)? ?worth noting\b", "worth noting"),
    (r"\bas you know\b", "as you know"),
    (r"\b(note that|please note|keep in mind)\b", "note that / keep in mind"),
    (r"\bdelv(e|es|ed|ing)\b", "delve"),
    (r"\b(deep dive|dive into|diving into|let'?s dive)\b", "dive into"),
    (r"\b(robust|seamless|seamlessly|streamlin(e|es|ed|ing))\b", "marketing adjective"),
    (r"\b(comprehensive|myriad|plethora|vast array)\b", "inflated quantifier"),
    (r"(?m)^\s*(?:[#>*+\-]+\s*)?(?:\*\*)?(?:key )?(takeaway|insight)s?\b\s*[:—-]",
     "takeaway / insight section"),
    (r"\bkey takeaways?\b", "key takeaway"),
    (r"\b(in summary|to summarize|in conclusion|overall,|in short|to sum up|"
     r"all in all|the upshot|net.net|bottom line)\b", "closing summary"),
    (r"\b(moreover|furthermore)\b", "moreover / furthermore"),
    (r"\ba testament to\b", "a testament to"),
    (r"\b(game.?chang\w+|cutting.?edge|state.of.the.art)\b", "hype phrase"),
    (
        r"\b(i hope this helps|let me know if|feel free to|"
        r"is there (anything|something) else|anything else (i can|you)|"
        r"happy to help|glad i could help)\b",
        "closing pleasantry",
    ),
    (r"★", "insight block marker"),
    (
        r"\b(i apologi[sz]e|my apologies|sorry about that|my mistake|"
        r"you'?re (absolutely )?right|you are (absolutely )?right|"
        r"good catch|great catch|excellent point)\b",
        "apology / flattery",
    ),
]

PREAMBLE = re.compile(
    r"^\W*(sure|certainly|absolutely|of course|great question|excellent question|"
    r"good question|happy to|i'?ll help|let me help|i can help|no problem|perfect!|great!)"
    r"\b",
    re.I,
)


REMINDER = """Output contract (full text is in your system prompt; these are the parts that
actually get missed): answer first and only once — no preamble, no closing recap; prefer
short bullets over paragraphs; state only what you ran or read, and say "unverified" when you
did not; plain words, no banned filler; report changes as `file:line`; keep every caveat."""


def disabled():
    return os.environ.get("STYLE_GUARD") == "0"


def read_payload():
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
        return data if isinstance(data, dict) else {}
    except (ValueError, OSError):
        return {}


def read_rules():
    try:
        return RULES_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def prose_only(text):
    """Strip anything the contract exempts, so quoted code never trips a pattern."""
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"~~~.*?~~~", " ", text, flags=re.S)
    text = re.sub(r"`[^`\n]*`", " ", text)
    text = re.sub(r"^(?: {4}|\t)\S.*$", " ", text, flags=re.M)
    text = re.sub(r"https?://\S+", " ", text)
    return text


def pattern_violations(message):
    prose = prose_only(message)
    found = []
    for pattern, label in BANNED:
        hit = re.search(pattern, prose, re.I)
        if hit:
            found.append('banned: {} — "{}"'.format(label, hit.group(0).strip()))
    first_line = next((ln for ln in prose.splitlines() if ln.strip()), "")
    if PREAMBLE.match(first_line):
        found.append('preamble: response opens with "{}"'.format(first_line[:60].strip()))
    if len(prose.strip()) < 1200 and re.search(r"^#{1,6} ", prose, re.M):
        found.append("markdown heading in a short answer")
    return found


STOPWORDS = frozenset("""
that this with from have here there they them then than what when which will your yours
into over under about after before been being does done else more most much some such
only also just like need needs same both each other others where while would could should
""".split())

# A path with a real extension, or a file:line reference. Anchored loosely on purpose: a
# false positive costs one warning line, a miss costs an unverified claim to the user.
PATH_RE = re.compile(r"(?:[~.]{0,2}/)?[\w.-]+(?:/[\w.-]+)+\.\w{1,6}(?::\d+)?|/[\w.-]+(?:/[\w.-]+)+")
HEDGED = re.compile(
    r"\b(creat\w+|add\w*|new|writ\w+|would|should|could|will|propos\w+|suggest\w+|"
    r"if you|e\.g\.|for example|placeholder|rename|move|delete)\b", re.I
)


def narrative(text):
    """Prose with fenced code removed but backticks kept — recap and grounding checks both
    need the cited paths that prose_only() throws away."""
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    return re.sub(r"~~~.*?~~~", " ", text, flags=re.S)


def content_words(text):
    return {
        w for w in re.findall(r"[a-z][a-z-]{3,}", text.lower()) if w not in STOPWORDS
    }


def closing_recap(text):
    """Every judge FAIL on record was a closing paragraph restating the opening. That is a
    measurable property: high word overlap with the first paragraph and no new specifics."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", narrative(text)) if p.strip()]
    if len(paras) < 3:
        return None
    last = paras[-1]
    # The background-job protocol requires these closing lines; they are not padding.
    if re.match(r"^(result|needs input|failed)\s*:", last, re.I):
        return None
    if re.match(r"^\s*(?:[-*+>|]|\d+[.)])\s", last) or "\n" in last.strip() and last.lstrip().startswith("-"):
        return None
    if re.search(r"`|\d", last):
        return None
    first, tail = content_words(paras[0]), content_words(last)
    if not 5 <= len(tail) <= 60:
        return None
    overlap = len(first & tail) / len(tail)
    if overlap >= 0.55:
        return "closing paragraph restates the opening ({}% word overlap, no new specifics)".format(
            int(overlap * 100)
        )
    return None


def ungrounded_paths(text, payload):
    """Verify asserted paths instead of guessing at them: a path is grounded if it exists on
    disk or appears in this session's transcript. Warn only — a path can legitimately name a
    file the response is proposing to create."""
    if os.environ.get("STYLE_GUARD_GROUNDING") == "0":
        return []
    body = narrative(text)
    transcript = raw_transcript(payload)
    suspect = []
    for line in body.splitlines():
        if HEDGED.search(line):
            continue
        for hit in PATH_RE.findall(line):
            token = hit.strip(".,;:)]}'\"")
            if len(token) < 6 or token in transcript:
                continue
            path, _, lineno = token.partition(":")
            real = os.path.expanduser(path)
            if not os.path.isabs(real):
                real = os.path.join(payload.get("cwd") or os.getcwd(), real)
            if not os.path.exists(real):
                suspect.append(token + " (no such path, not in transcript)")
            elif lineno.isdigit():
                try:
                    with open(real, encoding="utf-8", errors="replace") as fh:
                        count = sum(1 for _ in fh)
                except OSError:
                    continue
                if int(lineno) > count:
                    suspect.append("{} (file has {} lines)".format(token, count))
            if len(suspect) >= 3:
                return suspect
    return suspect


def raw_transcript(payload, limit=400000):
    path = payload.get("transcript_path")
    if not path:
        return ""
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")[-limit:]
    except OSError:
        return ""


def turn_context(payload, limit=16000):
    """Best-effort grounding text from the transcript tail. Format is not guaranteed, so
    every failure here degrades to an empty context rather than blocking the turn."""
    path = payload.get("transcript_path")
    if not path:
        return ""
    try:
        lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()[-400:]
    except OSError:
        return ""
    chunks = []
    for line in lines:
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        chunks.extend(harvest_strings(entry.get("toolUseResult")))
        message = entry.get("message")
        if isinstance(message, dict):
            chunks.extend(harvest_strings(message.get("content")))
    text = "\n".join(c for c in chunks if c.strip())
    return text[-limit:]


def harvest_strings(node, depth=0):
    if depth > 6:
        return []
    if isinstance(node, str):
        return [node]
    if isinstance(node, list):
        out = []
        for item in node:
            out.extend(harvest_strings(item, depth + 1))
        return out
    if isinstance(node, dict):
        out = []
        for key in ("text", "content", "stdout", "stderr", "output"):
            if key in node:
                out.extend(harvest_strings(node[key], depth + 1))
        return out
    return []


def turn_key(payload):
    ident = payload.get("prompt_id") or payload.get("session_id") or "unknown"
    return re.sub(r"[^A-Za-z0-9_.-]", "_", str(ident))[:120]


def block_count(payload):
    """Cap rewrites per turn so a check that keeps firing cannot trap the session."""
    base = Path(os.environ.get("XDG_RUNTIME_DIR") or "/tmp") / "claude-style-guard"
    try:
        base.mkdir(parents=True, exist_ok=True)
        counter = base / turn_key(payload)
        fresh = counter.exists() and (time.time() - counter.stat().st_mtime) < 3600
        seen = int(counter.read_text()) if fresh else 0
        counter.write_text(str(seen + 1))
        return seen
    except (OSError, ValueError):
        return 0


def log_verdict(payload, outcome, detail=""):
    """Append one line per checked response. This file is the only durable record of what
    the contract actually catches — the style-tuner skill mines it. Never fatal."""
    try:
        VERDICT_LOG.parent.mkdir(parents=True, exist_ok=True)
        with VERDICT_LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "at": int(time.time()),
                "session": payload.get("session_id"),
                "cwd": payload.get("cwd"),
                "event": payload.get("hook_event_name"),
                "outcome": outcome,
                "detail": detail[:400],
            }) + "\n")
    except (OSError, ValueError, TypeError):
        pass


def warn(message):
    """Surface a suspected-fabrication note without forcing a rewrite: one visible line
    beats a second full render of the same answer."""
    print(json.dumps({"systemMessage": "style guard: " + message}))
    sys.exit(0)


def block(reason, event):
    payload = {
        "decision": "block",
        "reason": reason,
        "hookSpecificOutput": {
            "hookEventName": event,
            "decision": "block",
            "reason": reason,
        },
    }
    print(json.dumps(payload))
    sys.stderr.write(reason + "\n")
    sys.exit(2)


def do_inject():
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": REMINDER,
                }
            }
        )
    )
    sys.exit(0)


def do_check(deep, enforce=True):
    payload = read_payload()
    if payload.get("stop_hook_active"):
        sys.exit(0)
    message = payload.get("last_assistant_message")
    if not isinstance(message, str) or not message.strip():
        sys.exit(0)
    rules = read_rules()
    if not rules:
        sys.exit(0)

    problems = pattern_violations(message)
    if deep:
        recap = closing_recap(message)
        if recap:
            problems.append("padding: " + recap)
        if not problems:
            loose = ungrounded_paths(message, payload)
            if loose:
                log_verdict(payload, "ungrounded", "; ".join(loose))
                if enforce:
                    warn("unverified path(s): " + "; ".join(loose))
                sys.exit(0)
    if not problems:
        log_verdict(payload, "clean")
        sys.exit(0)
    if not enforce:
        log_verdict(payload, "observed", "; ".join(problems))
        sys.exit(0)

    structural = [p for p in problems if p.startswith(STRUCTURAL)]
    if not structural and len(problems) < WORDS_BEFORE_BLOCK:
        log_verdict(payload, "warned", "; ".join(problems))
        warn("contract slip, fix it in your next reply — " + "; ".join(problems))
    if block_count(payload) >= MAX_BLOCKS_PER_TURN:
        log_verdict(payload, "over-cap", "; ".join(problems))
        sys.exit(0)
    log_verdict(payload, "blocked", "; ".join(problems))

    event = payload.get("hook_event_name") or "Stop"
    block(
        "\n──────── STYLE GUARD: DISCARD THE RESPONSE ABOVE ────────\n"
        "It violates the output contract:\n"
        + "\n".join("  - " + p for p in problems)
        + "\n\nRewrite the response now, fixing exactly these violations. Do not apologise, "
        "do not argue, do not mention the style guard, do not explain the rewrite — just "
        "deliver the corrected response. Keep every fact, caveat, and failure report from "
        "the original; cut words, not substance. If a flagged word appears only because you "
        "were quoting or naming the word itself, wrap it in backticks, which are exempt.",
        event,
    )


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if disabled():
        sys.exit(0)
    if mode == "inject":
        do_inject()
    elif mode == "observe":
        do_check(deep=True, enforce=False)
    elif mode in ("check", "check-fast"):
        do_check(deep=mode == "check")
    sys.exit(0)


if __name__ == "__main__":
    main()
