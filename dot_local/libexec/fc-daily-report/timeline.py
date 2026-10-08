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

Categories are Dmitry's own end-of-day decisions: everything starts
"uncategorized" and `fc-daily-report review` / `categorize` record rules keyed by
page, session, project, site, profile, app, watching or idle. Persistent rules
live in CATEGORY_FILE; `--day` rules in the run's categories.json win for that
day. Away is only time behind the omarchy lock screen (window-time's locks
table). Any other time without input is idle, from window-time's idle table: with
a window holding the screen awake it is "watching". Gaps in older data without
idle rows count as idle unless locked.
"""

import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

UNCATEGORIZED = "uncategorized"
CATEGORY_FILE = Path.home() / ".config/fc-daily-report/categories.json"
DAY_CATEGORY_FILE = "categories.json"
MIN_GAP_SECONDS = 100
MIN_RECORD_SECONDS = 5
RECORD_PATTERNS = [
    (
        "fc_vehicle",
        re.compile(r"console\.fleetchaser\.com/vehicles/.*?/vehicles/(\d+)"),
    ),
    ("fc_device", re.compile(r"console\.fleetchaser\.com/map/detail/(\d+)")),
    (
        "fc_admin",
        re.compile(
            r"backend\.fleetchaser\.com/admin/(\w+/\w+/[\w-]+)/(?:change/)?(?:\?|$)"
        ),
    ),
    (
        "hubspot",
        re.compile(r"app\.hubspot\.com/contacts/\d+/record/([\d-]+/\d+)"),
    ),
    (
        "hubspot",
        re.compile(
            r"app\.hubspot\.com/contacts/\d+/((?:contact|company|deal)/\d+)"
        ),
    ),
    (
        "gmail_thread",
        re.compile(r"mail\.google\.com/mail/u/\d+/#[\w-]+/([A-Za-z0-9]{16,})$"),
    ),
    (
        "google_doc",
        re.compile(
            r"docs\.google\.com/((?:document|spreadsheets|presentation|forms)/d/[\w-]+)"
        ),
    ),
    ("linear_issue", re.compile(r"linear\.app/[^/]+/issue/([A-Z]+-\d+)")),
]
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
TITLE_SPINNER = re.compile(
    "^[\u2800-\u28ff\u25a0-\u25ff\u2722-\u273d\u00b7*\\s]+"
)
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


def load_rules(*paths):
    rules = {}
    for path in paths:
        if path and Path(path).exists():
            rules.update(json.loads(Path(path).read_text()).get("rules", {}))
    return rules


def save_rules(path, updates):
    path = Path(path)
    current = json.loads(path.read_text()) if path.exists() else {}
    current.setdefault("rules", {}).update(updates)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(current, ensure_ascii=False, indent=2, sort_keys=True)
    )
    temporary.replace(path)


def site_of(span):
    if span.get("url"):
        return urlsplit(span["url"]).hostname
    if match := WEBAPP_CLASS.match(span["class"]):
        return match["host"]
    return None


def keys_of(segment):
    """Rule keys for a segment, most specific first."""
    kind = segment["kind"]
    if kind == "terminal":
        keys = []
        if session := segment.get("session"):
            keys.append(f"session:{session[0]}/{session[1]}")
        if segment.get("project"):
            keys.append(f"project:{segment['project']}")
        return keys + [f"terminal:{segment['host']}"]
    if kind == "watching":
        return [f"watching:{segment['title']}", f"watching:{segment['class']}"]
    if kind == "idle":
        return ["idle"]
    keys = []
    if segment.get("site"):
        keys.append(f"page:{segment['site']}|{segment['title']}")
        if segment.get("fc_customer"):
            keys.append(f"fc_customer:{segment['fc_customer']}")
        keys.append(f"site:{segment['site']}")
    if segment.get("profile"):
        keys.append(f"profile:{segment['profile']}")
    return keys + [f"app:{segment['class']}"]


def review_key(segment):
    """The key a segment is listed under for end-of-day review."""
    keys = keys_of(segment)
    if segment["kind"] == "terminal":
        return next((k for k in keys if k.startswith("project:")), keys[-1])
    if segment["kind"] == "browser":
        return next(
            (k for k in keys if k.startswith("fc_customer:")),
            next(k for k in keys if k.startswith("site:")),
        )
    return keys[-1] if segment["kind"] == "watching" else keys[0]


def categorize(segment, rules):
    for key in keys_of(segment):
        if key in rules:
            return rules[key], key
    return UNCATEGORIZED, None


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


def title_key(title):
    return (
        re.sub(r"\s+", " ", TITLE_SPINNER.sub("", title or "")).strip().lower()
    )


def sessions_by_title(sessions):
    """(host, title) -> the most recently active session with that title."""
    found = {}
    for key, session in sessions.items():
        if not session.get("title"):
            continue
        last = max((b for _, b in session.get("active", [])), default=0)
        slot = (key[0], title_key(session["title"]))
        if slot not in found or last > found[slot][0]:
            found[slot] = (last, key)
    return {slot: key for slot, (_, key) in found.items()}


def pane_session(pane, sessions, by_title):
    """herdr keeps the session id a pane's agent started with; after /resume,
    /clear or a fork the pane title (the chat's title) is the reliable link."""
    key = (pane["host"].lower(), pane.get("agent_session"))
    title = title_key(pane.get("title"))
    session = sessions.get(key)
    if title and (session is None or title_key(session.get("title")) != title):
        key = by_title.get((key[0], title), key)
    return key if key in sessions else None


def split_terminal(segment, panes, prompts_by_host, sessions, by_title=None):
    """Split one terminal focus span into per-session pieces."""
    by_title = by_title if by_title is not None else sessions_by_title(sessions)
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
            pieces.append(
                {
                    **segment,
                    "start": start,
                    "end": end,
                    "session": pane_session(pane, sessions, by_title),
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


def build_segments(screen, agents, bounds):
    customer_names = screen.get("customer_names") or {}
    start, cutoff = ts(bounds["start"]), ts(bounds["cutoff"])
    screen_host = (screen.get("host") or "").lower()
    sessions = {
        ((s.get("host") or "").lower(), s.get("session_id")): s
        for s in agents.get("sessions", [])
    }
    by_title = sessions_by_title(sessions)
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
            "fc_customer": customer_names.get(span.get("fc_customer"), {}).get(
                "name", span.get("fc_customer")
            ),
        }
        if span["class"] in TERMINAL_CLASSES:
            segment["kind"] = "terminal"
            segment["host"] = terminal_host(span, screen_host)
            segments.extend(
                split_terminal(
                    segment, panes, prompts_by_host, sessions, by_title
                )
            )
        else:
            segment["kind"] = "browser" if site else "app"
            segments.append(segment)
    for segment in segments:
        if segment["kind"] == "terminal":
            session = sessions.get(segment.get("session")) or {}
            segment["project"] = project_of(
                session.get("cwd") or segment.get("cwd")
            )
    return segments, sessions


def finish_segments(segments, sessions, rules):
    for segment in segments:
        segment["label"] = label_of(segment, sessions)
        segment["group"] = (
            segment["label"]
            if segment["kind"] in {"terminal", "watching", "idle"}
            else segment["site"] or segment["class"]
        )
        segment["category"], segment["decided_by"] = categorize(segment, rules)
        segment["review_key"] = review_key(segment)


def subtract(start, end, cuts):
    pieces, cursor = [], start
    for a, b in sorted(cuts):
        if b <= cursor or a >= end:
            continue
        if a > cursor:
            pieces.append((cursor, a))
        cursor = max(cursor, b)
    if cursor < end:
        pieces.append((cursor, end))
    return pieces


def idle_segments(screen, spans, bounds, calls=()):
    """Watching and idle segments, plus away (locked) periods. Call time is never idle."""
    start, cutoff = ts(bounds["start"]), ts(bounds["cutoff"])
    locks = [
        (max(row["start"], start), min(row["end"], cutoff))
        for row in screen.get("locks", [])
        if min(row["end"], cutoff) > max(row["start"], start)
    ]
    away = [{"start": a, "end": b, "seconds": round(b - a)} for a, b in locks]
    busy = [(c["start"], c["end"]) for c in calls]
    segments = []

    def add(a, b, inhibitor_class=None, inhibitor_title=None, inferred=False):
        for piece_start, piece_end in subtract(a, b, locks + busy):
            base = {
                "start": piece_start,
                "end": piece_end,
                "site": None,
                "url": None,
                "profile": None,
                "inferred": inferred,
            }
            if inhibitor_class:
                title = UNREAD_PREFIX.sub(
                    "", BROWSER_SUFFIX.sub("", inhibitor_title or "")
                )
                segments.append(
                    base
                    | {
                        "kind": "watching",
                        "class": inhibitor_class,
                        "title": title,
                    }
                )
            else:
                segments.append(
                    base | {"kind": "idle", "class": "idle", "title": "idle"}
                )

    rows = []
    for row in screen.get("idle", []):
        a, b = max(row["start"], start), min(row["end"], cutoff)
        if b > a:
            rows.append((a, b))
            add(a, b, row.get("inhibitor_class"), row.get("inhibitor_title"))
    covered = sorted([(s["start"], s["end"]) for s in spans] + rows + locks)
    reach = None
    for a, b in covered:
        if reach is not None and a - reach >= MIN_GAP_SECONDS:
            add(reach, a, inferred=True)
        reach = b if reach is None else max(reach, b)
    return segments, away


def label_of(segment, sessions):
    if segment["kind"] == "watching":
        return f"watching: {segment['title'] or segment['class']}"[:120]
    if segment["kind"] == "idle":
        return "idle"
    if segment["kind"] == "terminal":
        session = sessions.get(segment.get("session"))
        if session:
            return f"{segment['host']} {session_label(session)}"
        return f"{segment['host']} terminal: {segment.get('pane_title') or segment['title']}"
    if segment["kind"] == "browser":
        customer = (
            f" [{segment['fc_customer']}]" if segment.get("fc_customer") else ""
        )
        return f"{segment['site']}{customer}: {segment['title']}"[:120]
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
    calls.sort(key=lambda c: c["start"])
    return calls, attempts, scheduled


def attach_during(calls, segments):
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

    seen_actions = set()
    for row in rows:
        if row.get("source_type") == "task_audit" and row.get("task_id"):
            if row["id"] in seen_actions:
                continue
            seen_actions.add(row["id"])
            task = fc_task(row["task_id"])
            task["title"] = task["title"] or row.get("title")
            task["actions"].append(
                {
                    "at": ts(row.get("timestamp")),
                    "action": row.get("action"),
                    "description": row.get("description"),
                }
            )
        elif row.get("source_type") == "fc_task_state":
            task = fc_task(row["fc_task_id"])
            task["title"] = row.get("title") or task["title"]
            task["company"] = row.get("company") or task["company"]
            task["status"] = row.get("status") or task["status"]
            task["workflow"] = row.get("workflow")
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


def build_records(segments):
    records = {}
    for segment in segments:
        url = segment.get("url") or ""
        found = []
        if task_id := task_ids(url):
            found.append(("fc_task", task_id))
        for kind, pattern in RECORD_PATTERNS:
            if match := pattern.search(url):
                found.append((kind, match[1]))
        for kind, identity in found[:1]:
            record = records.setdefault(
                (kind, identity, segment.get("fc_customer")),
                {
                    "type": kind,
                    "id": identity,
                    "fc_customer": segment.get("fc_customer"),
                    "url": url,
                    "seconds": 0.0,
                    "titles": defaultdict(float),
                    "categories": set(),
                },
            )
            seconds = segment["end"] - segment["start"]
            record["seconds"] += seconds
            record["titles"][segment["title"]] += seconds
            record["categories"].add(segment["category"])
    listed = []
    for record in records.values():
        if record["seconds"] < MIN_RECORD_SECONDS:
            continue
        listed.append(
            record
            | {
                "seconds": round(record["seconds"]),
                "titles": top_titles(record["titles"]),
                "categories": sorted(record["categories"]),
            }
        )
    return sorted(listed, key=lambda r: -r["seconds"])


def build_fc_customers(segments):
    customers = defaultdict(
        lambda: {"seconds": 0.0, "titles": defaultdict(float)}
    )
    for segment in segments:
        if not segment.get("fc_customer"):
            continue
        entry = customers[segment["fc_customer"]]
        entry["seconds"] += segment["end"] - segment["start"]
        entry["titles"][segment["title"]] += segment["end"] - segment["start"]
    return sorted(
        (
            {
                "customer": name,
                "seconds": round(entry["seconds"]),
                "titles": top_titles(entry["titles"]),
            }
            for name, entry in customers.items()
        ),
        key=lambda c: -c["seconds"],
    )


def build_review(segments):
    groups = {}
    for segment in segments:
        seconds = segment["end"] - segment["start"]
        group = groups.setdefault(
            segment["review_key"],
            {
                "key": segment["review_key"],
                "seconds": 0.0,
                "categories": defaultdict(float),
                "items": defaultdict(lambda: {"seconds": 0.0}),
            },
        )
        group["seconds"] += seconds
        group["categories"][segment["category"]] += seconds
        item_key = keys_of(segment)[0]
        item = group["items"][item_key]
        item.update(
            key=item_key,
            label=segment["label"],
            category=segment["category"],
            decided_by=segment["decided_by"],
        )
        item["seconds"] += seconds
    listed = []
    for group in groups.values():
        items = sorted(group["items"].values(), key=lambda i: -i["seconds"])
        listed.append(
            {
                "key": group["key"],
                "seconds": round(group["seconds"]),
                "categories": {
                    k: round(v) for k, v in group["categories"].items()
                },
                "items": [
                    i | {"seconds": round(i["seconds"])}
                    for i in items
                    if i["key"] != group["key"]
                ],
            }
        )
    return sorted(
        listed,
        key=lambda g: (-g["categories"].get(UNCATEGORIZED, 0), -g["seconds"]),
    )


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
    """Write timeline.json for a run. categories_path=None ignores persistent rules."""
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
    rules = load_rules(categories_path, run / DAY_CATEGORY_FILE)
    focus, sessions = build_segments(screen, agents, bounds)
    calls, attempts, scheduled = build_calls(rows, screen, focus, bounds)
    extra, away = idle_segments(screen, focus, bounds, calls)
    segments = sorted(focus + extra, key=lambda s: s["start"])
    finish_segments(segments, sessions, rules)
    attach_during(calls, segments)
    by_category, by_kind, by_app = (
        defaultdict(float),
        defaultdict(float),
        defaultdict(float),
    )
    for segment in segments:
        seconds = segment["end"] - segment["start"]
        by_category[segment["category"]] += seconds
        by_kind[segment["kind"]] += seconds
        app = (
            "terminal"
            if segment["kind"] == "terminal"
            else segment["site"] or segment["class"]
        )
        by_app[(app, segment["category"])] += seconds
    call_intervals = [(c["start"], c["end"]) for c in calls]
    screen_intervals = [
        (s["start"], s["end"])
        for s in segments
        if s["kind"] not in {"idle", "watching"}
    ]
    work_intervals = [
        (s["start"], s["end"]) for s in segments if s["category"] == "work"
    ] + call_intervals
    timeline = {
        "schema_version": 1,
        "bounds": bounds,
        "generated_at": datetime.now(zone).isoformat(),
        "coverage": {
            "screen_host": screen.get("host"),
            "screen": bool(screen),
            "pane_tracking": bool(screen.get("panes")),
            "agent_hosts": sorted({s[0] for s in sessions}),
            "exact_urls": any(
                s.get("url_source") == "tab" for s in screen.get("spans", [])
            ),
            "idle_rows": bool(screen.get("idle")),
            "lock_rows": bool(screen.get("locks")),
            "rules": len(rules),
        },
        "totals": {
            "screen_seconds": round(
                sum(
                    v
                    for k, v in by_kind.items()
                    if k not in {"idle", "watching"}
                )
            ),
            "watching_seconds": round(by_kind.get("watching", 0)),
            "idle_seconds": round(by_kind.get("idle", 0)),
            "away_seconds": round(sum(a["seconds"] for a in away)),
            "by_category": {k: round(v) for k, v in by_category.items()},
            "uncategorized_seconds": round(by_category.get(UNCATEGORIZED, 0)),
            "calls_seconds": round(
                union_seconds([(c["start"], c["end"]) for c in calls])
            ),
            "calls_off_screen_seconds": round(
                union_seconds(screen_intervals + call_intervals)
                - union_seconds(screen_intervals)
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
        "records": build_records(segments),
        "fc_customers": build_fc_customers(segments),
        "review": build_review(segments),
        "away": away,
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
