"""Build a measured timeline from a collected run (no remote reads).

Usage: fc-daily-report timeline --run RUN_DIR [--categories PATH]
Reads screen.json, agents.json and sources.json from the run and writes
timeline.json: totals by category, terminal time per Claude/Codex session,
calls (Dialpad durations, Meet time measured on the desktop) with the screen
activity during each call, tasks touched, and chronological blocks.

Measured: window focus on the --screen-host desktop, Dialpad connect-to-end, and
the desktop's mic-in-use intervals. Not measured: work away from that desktop
other than Dialpad calls, and meetings joined on another device (calendar time
is reported separately as scheduled). Terminal time goes to the herdr pane that
had focus; before pane tracking existed it goes to the session most recently
prompted on that host ("prompt-inferred").
"""

import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

DEFAULT_CATEGORIES = {
    "default": "work",
    "profiles": {"Personal": "personal", "CER": "cer", "BulkBid": "bulkbid"},
    "classes": {"spotify": "personal"},
    "sites": {},
}
CATEGORY_FILE = Path.home() / ".config/fc-daily-report/categories.json"
TERMINAL_CLASSES = {
    "com.mitchellh.ghostty",
    "org.omarchy.agent",
    "org.omarchy.terminal",
    "kitty",
    "foot",
    "Alacritty",
}
SCRATCHPAD_CLASS = "org.omarchy.agent"
TITLE_HOST = re.compile(r"^(?P<host>[\w.-]+): ")
WEBAPP_CLASS = re.compile(r"^chrome-(?P<host>.+?)__")
BROWSER_SUFFIX = re.compile(r" - (Chromium|Google Chrome)$")
UNREAD_PREFIX = re.compile(r"^\(\d+\)\s*")
MEET_CODE = re.compile(r"\b([a-z]{3}-[a-z]{4}-[a-z]{3})\b")
LINEAR_ISSUE = re.compile(r"linear\.app/[^/]+/issue/([A-Z]+-\d+)")
SAME_CALL_SHARE = 0.5
MAX_MEETING_SECONDS = 12 * 3600
BLOCK_MERGE_GAP = 60
MIN_BLOCK_SECONDS = 60
TOP_TITLES = 3
TOP_DURING_CALL = 8


def ts(value):
    if value in (None, "", "None"):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def overlap(a_start, a_end, b_start, b_end):
    return max(0.0, min(a_end, b_end) - max(a_start, b_start))


def union_seconds(intervals):
    total, current = 0.0, None
    for start, end in sorted(intervals):
        if current and start <= current[1]:
            current[1] = max(current[1], end)
            continue
        if current:
            total += current[1] - current[0]
        current = [start, end]
    return total + (current[1] - current[0] if current else 0.0)


def load_categories(path):
    rules = json.loads(json.dumps(DEFAULT_CATEGORIES))
    if path and Path(path).exists():
        for key, value in json.loads(Path(path).read_text()).items():
            if isinstance(value, dict):
                rules.setdefault(key, {}).update(value)
            else:
                rules[key] = value
    return rules


def site_of(span):
    if span.get("url"):
        return urlsplit(span["url"]).hostname
    if match := WEBAPP_CLASS.match(span["class"]):
        return match["host"]
    return None


def category_of(span, site, rules):
    if span.get("profile") in rules["profiles"]:
        return rules["profiles"][span["profile"]]
    if span["class"] in rules["classes"]:
        return rules["classes"][span["class"]]
    for pattern, category in rules["sites"].items():
        if site and (site == pattern or site.endswith("." + pattern)):
            return category
    return rules["default"]


def terminal_host(span, screen_host):
    if span["class"] == SCRATCHPAD_CLASS:
        return screen_host
    match = TITLE_HOST.match(span.get("title") or "")
    return match["host"].lower() if match else screen_host


def session_label(session):
    title = session.get("title") or "untitled session"
    return f"{session['agent']}: {title}"


def project_of(cwd):
    return Path(cwd).name if cwd else None


def split_terminal(segment, panes, prompts_by_host, sessions):
    """Split one terminal focus span into per-session pieces."""
    host = segment["host"]
    pieces, cursor = [], segment["start"]
    covered = sorted(
        (max(p["start"], segment["start"]), min(p["end"], segment["end"]), p)
        for p in panes
        if overlap(p["start"], p["end"], segment["start"], segment["end"]) > 0
    )
    for start, end, pane in covered + [(segment["end"], segment["end"], None)]:
        if start > cursor:
            pieces.extend(
                inferred(segment, cursor, start, prompts_by_host.get(host, []))
            )
        if pane is not None:
            key = (pane["host"].lower(), pane.get("agent_session"))
            session = sessions.get(key)
            pieces.append(
                {
                    **segment,
                    "start": start,
                    "end": end,
                    "session": key if session else None,
                    "agent": pane.get("agent"),
                    "pane_title": pane.get("title"),
                    "cwd": pane.get("cwd"),
                    "attribution": "herdr",
                }
            )
        cursor = max(cursor, end)
    return pieces


def inferred(segment, start, end, prompts):
    times = [at for at, _ in prompts]
    cuts = [start] + [at for at in times if start < at < end] + [end]
    pieces = []
    for a, b in zip(cuts, cuts[1:], strict=False):
        latest = None
        for at, key in prompts:
            if at <= a:
                latest = key
            else:
                break
        pieces.append(
            {
                **segment,
                "start": a,
                "end": b,
                "session": latest,
                "attribution": "prompt-inferred" if latest else "none",
            }
        )
    return pieces


def build_segments(screen, agents, bounds, rules):
    start, cutoff = ts(bounds["start"]), ts(bounds["cutoff"])
    screen_host = (screen.get("host") or "").lower()
    sessions = {
        ((s.get("host") or "").lower(), s.get("session_id")): s
        for s in agents.get("sessions", [])
    }
    prompts_by_host = defaultdict(list)
    for key, session in sessions.items():
        for prompt in session.get("prompts", []):
            prompts_by_host[key[0]].append((prompt["at"], key))
    for prompts in prompts_by_host.values():
        prompts.sort()
    panes = [p for p in screen.get("panes", []) if p["end"] > p["start"]]
    segments = []
    for span in screen.get("spans", []):
        a, b = max(span["start"], start), min(span["end"], cutoff)
        if b <= a:
            continue
        site = site_of(span)
        title = UNREAD_PREFIX.sub(
            "", BROWSER_SUFFIX.sub("", span.get("title") or "")
        )
        segment = {
            "start": a,
            "end": b,
            "class": span["class"],
            "title": title,
            "url": span.get("url"),
            "profile": span.get("profile"),
            "site": site,
            "category": category_of(span, site, rules),
        }
        if span["class"] in TERMINAL_CLASSES:
            segment["kind"] = "terminal"
            segment["host"] = terminal_host(span, screen_host)
            segments.extend(
                split_terminal(segment, panes, prompts_by_host, sessions)
            )
        else:
            segment["kind"] = "browser" if site else "app"
            segments.append(segment)
    for segment in segments:
        segment["label"] = label_of(segment, sessions)
        segment["group"] = (
            segment["label"]
            if segment["kind"] == "terminal"
            else segment["site"] or segment["class"]
        )
    return segments, sessions


def label_of(segment, sessions):
    if segment["kind"] == "terminal":
        session = sessions.get(segment.get("session"))
        if session:
            return f"{segment['host']} {session_label(session)}"
        return f"{segment['host']} terminal: {segment.get('pane_title') or segment['title']}"
    if segment["kind"] == "browser":
        return f"{segment['site']}: {segment['title']}"[:120]
    return segment["class"]


def dialpad_calls(rows):
    seen, calls, attempts = set(), [], []
    for row in rows:
        if row.get("source_type") != "call":
            continue
        key = row.get("dialpad_call_id") or row["id"]
        if key in seen:
            continue
        seen.add(key)
        connected, ended = ts(row.get("connected_at")), ts(row.get("ended_at"))
        info = {
            "kind": "dialpad",
            "ref": row.get("ref") or f"call:{row['id']}",
            "company": row.get("company"),
            "direction": row.get("direction"),
            "dialpad_seconds": row.get("duration_seconds"),
        }
        if connected and ended and ended > connected:
            calls.append(
                info
                | {"start": connected, "end": ended, "measured_by": "dialpad"}
            )
        else:
            attempts.append(info | {"at": ts(row.get("timestamp"))})
    return calls, attempts


def meet_codes_during(segments, start, end):
    codes = defaultdict(float)
    for segment in segments:
        seconds = overlap(segment["start"], segment["end"], start, end)
        if not seconds:
            continue
        text = f"{segment.get('title') or ''} {segment.get('url') or ''}"
        if "meet.google.com" in text or text.startswith("Meet - "):
            for code in MEET_CODE.findall(text):
                codes[code] += seconds
    return max(codes, key=codes.get) if codes else None


def calendar_events(rows):
    events = []
    for row in rows:
        if row.get("source_type") != "calendar_event":
            continue
        start, end = ts(row.get("timestamp")), ts(row.get("end"))
        if not start or not end or not 0 < end - start < MAX_MEETING_SECONDS:
            continue
        if (row.get("status") or "") == "cancelled":
            continue
        link = row.get("meet_link") or ""
        code = MEET_CODE.search(link)
        events.append(
            {
                "ref": row.get("ref") or f"calendar_event:{row['id']}",
                "title": row.get("title"),
                "start": start,
                "end": end,
                "meet_code": code[1] if code else None,
            }
        )
    return events


def build_calls(rows, screen, segments, bounds):
    start, cutoff = ts(bounds["start"]), ts(bounds["cutoff"])
    calls, attempts = dialpad_calls(rows)
    events = calendar_events(rows)
    for local in screen.get("calls", []):
        a, b = max(local["start"], start), min(local["end"], cutoff)
        if b <= a:
            continue
        shared = sum(overlap(a, b, c["start"], c["end"]) for c in calls)
        if shared >= SAME_CALL_SHARE * (b - a):
            continue
        code = meet_codes_during(segments, a, b)
        event = next(
            (e for e in events if code and e["meet_code"] == code), None
        )
        if event is None and code is None:
            event = max(
                events,
                key=lambda e: overlap(a, b, e["start"], e["end"]),
                default=None,
            )
            if event and not overlap(a, b, event["start"], event["end"]):
                event = None
        calls.append(
            {
                "kind": "meet" if code else "call",
                "start": a,
                "end": b,
                "measured_by": "desktop microphone",
                "apps": local.get("apps"),
                "meet_code": code,
                "event": event["title"] if event else None,
                "event_ref": event["ref"] if event else None,
            }
        )
    matched = {c.get("event_ref") for c in calls}
    scheduled = [
        e | {"seconds": e["end"] - e["start"]}
        for e in events
        if e["ref"] not in matched
    ]
    for call in calls:
        call["seconds"] = call["end"] - call["start"]
        during = defaultdict(float)
        for segment in segments:
            seconds = overlap(
                segment["start"], segment["end"], call["start"], call["end"]
            )
            if seconds:
                during[segment["label"]] += seconds
        call["screen_seconds"] = sum(during.values())
        call["during"] = [
            {"label": label, "seconds": round(seconds)}
            for label, seconds in sorted(during.items(), key=lambda i: -i[1])
        ][:TOP_DURING_CALL]
    calls.sort(key=lambda c: c["start"])
    return calls, attempts, scheduled


def build_terminal(segments, sessions):
    by_session = defaultdict(float)
    by_host = defaultdict(float)
    unattributed = defaultdict(float)
    attribution = defaultdict(float)
    for segment in segments:
        if segment["kind"] != "terminal":
            continue
        seconds = segment["end"] - segment["start"]
        by_host[segment["host"]] += seconds
        attribution[segment.get("attribution", "none")] += seconds
        if segment.get("session") in sessions:
            by_session[segment["session"]] += seconds
        else:
            unattributed[segment.get("pane_title") or segment["title"]] += (
                seconds
            )
    listed = []
    for key, session in sessions.items():
        listed.append(
            {
                "host": key[0],
                "agent": session.get("agent"),
                "session_id": session.get("session_id"),
                "title": session.get("title"),
                "project": project_of(session.get("cwd")),
                "cwd": session.get("cwd"),
                "branch": session.get("branch"),
                "focus_seconds": round(by_session.get(key, 0)),
                "agent_active_seconds": round(
                    sum(b - a for a, b in session.get("active", []))
                ),
                "prompts": session.get("prompts", []),
            }
        )
    listed.sort(key=lambda s: (-s["focus_seconds"], -len(s["prompts"])))
    return {
        "seconds": round(sum(by_host.values())),
        "by_host": {k: round(v) for k, v in by_host.items()},
        "attribution_seconds": {k: round(v) for k, v in attribution.items()},
        "sessions": listed,
        "unattributed": [
            {"window": k, "seconds": round(v)}
            for k, v in sorted(unattributed.items(), key=lambda i: -i[1])
        ],
    }


def task_ids(url):
    if not url:
        return None
    values = parse_qs(urlsplit(url).query).get("taskId")
    return values[0] if values else None


def build_tasks(rows, segments, task_names):
    fc = {}

    def fc_task(task_id):
        return fc.setdefault(
            str(task_id),
            {
                "fc_task_id": str(task_id),
                "title": None,
                "company": None,
                "status": None,
                "actions": [],
                "modified_unattributed": False,
                "screen_seconds": 0.0,
            },
        )

    for row in rows:
        if row.get("source_type") == "task_audit" and row.get("task_id"):
            task = fc_task(row["task_id"])
            task["title"] = task["title"] or row.get("title")
            task["actions"].append(
                {"at": ts(row.get("timestamp")), "action": row.get("action")}
            )
        elif row.get("source_type") == "task" and row.get("fc_task_id"):
            task = fc_task(row["fc_task_id"])
            task["title"] = task["title"] or row.get("title")
            task["company"] = task["company"] or row.get("company")
            task["status"] = row.get("status_name")
            task["modified_unattributed"] = True
    for segment in segments:
        if task_id := task_ids(segment.get("url")):
            fc_task(task_id)["screen_seconds"] += (
                segment["end"] - segment["start"]
            )
    for task_id, info in (task_names or {}).items():
        if task_id in fc:
            for key in ["title", "company", "status"]:
                fc[task_id][key] = fc[task_id][key] or info.get(key)
    linear = {}
    for row in rows:
        if row.get("source_type") != "linear_live" or not row.get("identifier"):
            continue
        issue = linear.setdefault(
            row["identifier"],
            {
                "identifier": row["identifier"],
                "title": row.get("title"),
                "url": row.get("url"),
                "events": 0,
                "state_changes": [],
                "screen_seconds": 0.0,
            },
        )
        issue["events"] += 1
        if row.get("to_state"):
            issue["state_changes"].append(
                {
                    "at": ts(row.get("timestamp")),
                    "to": (row["to_state"] or {}).get("name")
                    if isinstance(row["to_state"], dict)
                    else row["to_state"],
                }
            )
    for segment in segments:
        if match := LINEAR_ISSUE.search(segment.get("url") or ""):
            if match[1] in linear:
                linear[match[1]]["screen_seconds"] += (
                    segment["end"] - segment["start"]
                )
    for item in list(fc.values()) + list(linear.values()):
        item["screen_seconds"] = round(item["screen_seconds"])
    return {
        "fc": sorted(
            fc.values(),
            key=lambda t: (-len(t["actions"]), -t["screen_seconds"]),
        ),
        "linear": sorted(linear.values(), key=lambda i: -i["events"]),
    }


def top_titles(titles):
    return [
        {"title": title, "seconds": round(seconds)}
        for title, seconds in sorted(titles.items(), key=lambda i: -i[1])[
            :TOP_TITLES
        ]
    ]


def build_blocks(segments, zone):
    blocks = []
    for segment in sorted(segments, key=lambda s: s["start"]):
        seconds = segment["end"] - segment["start"]
        last = blocks[-1] if blocks else None
        if not (
            last
            and last["group"] == segment["group"]
            and segment["start"] - last["end"] <= BLOCK_MERGE_GAP
        ):
            last = {
                "start": segment["start"],
                "end": segment["end"],
                "seconds": 0.0,
                "group": segment["group"],
                "category": segment["category"],
                "titles": defaultdict(float),
            }
            blocks.append(last)
        last["end"] = max(last["end"], segment["end"])
        last["seconds"] += seconds
        last["titles"][segment["title"] or segment["label"]] += seconds
    kept = [b for b in blocks if b["seconds"] >= MIN_BLOCK_SECONDS]
    for block in kept:
        block["local"] = (
            f"{datetime.fromtimestamp(block['start'], zone):%H:%M}"
            f"–{datetime.fromtimestamp(block['end'], zone):%H:%M}"
        )
        block["seconds"] = round(block["seconds"])
        block["titles"] = top_titles(block["titles"])
    return kept


def build_buckets(segments, calls, zone, minutes):
    size = minutes * 60
    buckets = {}
    for segment in segments:
        cursor = segment["start"]
        while cursor < segment["end"]:
            local = datetime.fromtimestamp(cursor, zone)
            first = local.replace(
                minute=local.minute // minutes * minutes,
                second=0,
                microsecond=0,
            ).timestamp()
            stop = min(segment["end"], first + size)
            bucket = buckets.setdefault(
                first,
                {
                    "categories": defaultdict(float),
                    "groups": defaultdict(float),
                },
            )
            bucket["categories"][segment["category"]] += stop - cursor
            bucket["groups"][segment["group"]] += stop - cursor
            cursor = stop
    listed = []
    for first, bucket in sorted(buckets.items()):
        listed.append(
            {
                "local": f"{datetime.fromtimestamp(first, zone):%H:%M}",
                "screen_seconds": round(sum(bucket["categories"].values())),
                "categories": {
                    k: round(v) for k, v in bucket["categories"].items()
                },
                "call_seconds": round(
                    union_seconds(
                        [
                            (
                                max(c["start"], first),
                                min(c["end"], first + size),
                            )
                            for c in calls
                            if overlap(
                                c["start"], c["end"], first, first + size
                            )
                        ]
                    )
                ),
                "top": top_titles(bucket["groups"]),
            }
        )
    return listed


def build(run, categories_path=CATEGORY_FILE):
    run = Path(run)
    manifest = json.loads((run / "manifest.json").read_text())
    bucket_minutes = manifest["config"].get("timeline_bucket_minutes", 30)
    bounds = manifest["bounds"]
    zone = ZoneInfo(bounds["timezone"])
    screen = _read(run / "screen.json", {})
    agents = _read(run / "agents.json", {})
    sources = _read(run / "sources.json", {})
    rows = [
        row for source in sources.values() for row in source.get("rows", [])
    ]
    rules = load_categories(categories_path)
    segments, sessions = build_segments(screen, agents, bounds, rules)
    calls, attempts, scheduled = build_calls(rows, screen, segments, bounds)
    by_category, by_app = defaultdict(float), defaultdict(float)
    for segment in segments:
        seconds = segment["end"] - segment["start"]
        by_category[segment["category"]] += seconds
        app = (
            "terminal"
            if segment["kind"] == "terminal"
            else segment["site"] or segment["class"]
        )
        by_app[(app, segment["category"])] += seconds
    work_intervals = [
        (s["start"], s["end"]) for s in segments if s["category"] == "work"
    ] + [(c["start"], c["end"]) for c in calls]
    timeline = {
        "schema_version": 1,
        "bounds": bounds,
        "generated_at": datetime.now(zone).isoformat(),
        "coverage": {
            "screen_host": screen.get("host"),
            "screen": bool(screen),
            "pane_tracking": bool(screen.get("panes")),
            "agent_hosts": sorted({s[0] for s in sessions}),
            "categories_file": str(categories_path)
            if categories_path and Path(categories_path).exists()
            else None,
        },
        "totals": {
            "screen_seconds": round(sum(by_category.values())),
            "by_category": {k: round(v) for k, v in by_category.items()},
            "calls_seconds": round(
                union_seconds([(c["start"], c["end"]) for c in calls])
            ),
            "calls_off_screen_seconds": round(
                union_seconds(work_intervals)
                - union_seconds(
                    [
                        (s["start"], s["end"])
                        for s in segments
                        if s["category"] == "work"
                    ]
                )
            ),
            "work_seconds": round(union_seconds(work_intervals)),
            "scheduled_unmeasured_meeting_seconds": round(
                union_seconds([(e["start"], e["end"]) for e in scheduled])
            ),
        },
        "apps": [
            {"app": app, "category": category, "seconds": round(seconds)}
            for (app, category), seconds in sorted(
                by_app.items(), key=lambda i: -i[1]
            )
        ],
        "terminal": build_terminal(segments, sessions),
        "calls": calls,
        "call_attempts": attempts,
        "scheduled_meetings": scheduled,
        "tasks": build_tasks(rows, segments, screen.get("task_names")),
        "blocks": build_blocks(segments, zone),
        "buckets": build_buckets(segments, calls, zone, bucket_minutes),
    }
    _write(run / "timeline.json", timeline)
    return timeline


def _read(path, default):
    return json.loads(path.read_text()) if path.exists() else default


def _write(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2))
    temporary.chmod(0o600)
    temporary.replace(path)
