#!/usr/bin/env python3
"""mine.py — report what the output contract actually caught, so it can be tuned on evidence.

Usage:  python3 ~/.claude/skills/style-tuner/mine.py [--days N] [--examples N]

Reads two sources and prints one plain-text report:
  1. $XDG_STATE_HOME/claude-style-guard/verdicts.jsonl — written by style-guard.py on every
     checked response (outcome: clean / blocked / over-cap / judge-warn). This is the good
     data, but only exists for turns since logging was added.
  2. ~/.claude/projects/**/*.jsonl — transcripts, grepped for the block banner. This is the
     only record of blocks that predate the log, and it undercounts.

No writes, no network, no deps. Safe to run any time.
"""

import argparse
import collections
import glob
import json
import os
import re
import time
from pathlib import Path

STATE = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state")
LOG = STATE / "claude-style-guard" / "verdicts.jsonl"
TRANSCRIPTS = Path.home() / ".claude" / "projects"
BANNER = "It violates the output contract:"


def load_log(cutoff):
    rows = []
    try:
        for line in LOG.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict) and row.get("at", 0) >= cutoff:
                rows.append(row)
    except OSError:
        pass
    return rows


def load_transcript_blocks():
    """Historical blocks, deduped per (file, violation) because the banner is echoed more
    than once per block in the transcript JSON."""
    seen, found = set(), []
    for path in glob.glob(str(TRANSCRIPTS / "**" / "*.jsonl"), recursive=True):
        try:
            blob = Path(path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if BANNER not in blob:
            continue
        for match in re.finditer(re.escape(BANNER) + r"\\n((?:  - [^\\]+\\n?)+)", blob):
            for item in match.group(1).replace("\\n", "\n").splitlines():
                item = item.strip().lstrip("- ").strip().rstrip("\\ ").strip()
                key = (path, item)
                if item and key not in seen:
                    seen.add(key)
                    found.append((Path(path).name[:8], item))
    return found


def category(detail):
    detail = detail.strip()
    if detail.startswith("padding:"):
        return "padding", "closing recap"
    if "no such path" in detail or "file has" in detail:
        return "ungrounded-path", detail.split(" (")[0][:60]
    if detail.upper().startswith(("FAIL", "WARN")):
        return "legacy-judge", detail[:90]
    if detail.startswith("banned:"):
        return "banned-word", detail.split("—")[0].replace("banned:", "").strip()
    if detail.startswith("preamble"):
        return "preamble", "opener"
    if detail.startswith("markdown heading"):
        return "heading", "short answer"
    return "other", detail[:60]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--examples", type=int, default=6)
    args = ap.parse_args()
    cutoff = time.time() - args.days * 86400

    rows = load_log(cutoff)
    outcomes = collections.Counter(r.get("outcome") for r in rows)
    total = sum(outcomes.values())

    print(f"=== verdict log ({args.days}d) — {LOG} ===")
    if not total:
        print("no entries yet; logging starts with the next checked response\n")
    else:
        clean = outcomes.get("clean", 0)
        print(f"responses checked: {total}   clean: {clean} ({100*clean//total}%)")
        for name, count in outcomes.most_common():
            if name != "clean":
                print(f"  {name:12} {count}")
        print()

    buckets = collections.Counter()
    samples = collections.defaultdict(list)
    for row in rows:
        detail = (row.get("detail") or "").strip()
        if not detail:
            continue
        for piece in detail.split("; "):
            kind, label = category(piece)
            buckets[(kind, label)] += 1
            if len(samples[(kind, label)]) < args.examples:
                samples[(kind, label)].append(row.get("cwd") or "?")

    if buckets:
        print("=== what fired, most frequent first ===")
        for (kind, label), count in buckets.most_common():
            print(f"{count:4}  [{kind}] {label}")
        print()

    hist = load_transcript_blocks()
    if hist:
        print(f"=== historical blocks found in transcripts ({len(hist)} unique) ===")
        for kind, count in collections.Counter(
            category(item)[0] for _, item in hist
        ).most_common():
            print(f"{count:4}  {kind}")
        print()
        for sid, item in hist[: args.examples]:
            print(f"  {sid}  {item}")
        print()

    print("=== read this as ===")
    print("high banned-word count on one word  -> the word is legitimate here; drop it")
    print("high preamble/heading count         -> tighten rule 1/7 wording, not the regex")
    print("high padding count                  -> rule 1 is not landing; sharpen its wording")
    print("high ungrounded-path count          -> real fabrication, or PATH_RE is too greedy;")
    print("                                       check a few by hand before changing rule 3")
    print("clean rate already >95%             -> leave it alone")


main()
