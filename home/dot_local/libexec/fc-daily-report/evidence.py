"""Daily-report evidence adapters; imported by collect.py and fixture tests.

Standard library only. All adapters redact before returning or persisting data.
Discovery snippets are not complete evidence; use document references for judging outcomes.
"""

import base64
import re
from datetime import UTC, date, datetime, time, timedelta
from email.utils import getaddresses
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

SECRET_LABEL = re.compile(
    r"(?i)\b(api[ _-]?key|access[ _-]?token|refresh[ _-]?token|"
    r"password|secret|verification code|pin)\b"
    r"(?:\s+(?:for (?:their|your|the) account|is))?\s*[:=]\s*\S+"
)
URL = re.compile(r"https?://[^\s<>\"']+")
SECRET_QUERY_KEYS = {
    "code",
    "state",
    "token",
    "access_token",
    "refresh_token",
    "id_token",
    "password",
    "secret",
    "key",
    "api_key",
    "signature",
    "session",
    "sid",
}


def redact_url(value):
    parts = urlsplit(value)
    if re.search(
        r"(?i)(lb_ak_|fckb_|reset[-_/]?password|magic[-_/]?link)", parts.path
    ):
        return f"{parts.scheme}://{parts.hostname}/[redacted-access-link]"
    netloc = parts.netloc.rsplit("@", 1)[-1]
    query = urlencode(
        [
            (key, "[redacted]" if key.lower() in SECRET_QUERY_KEYS else item)
            for key, item in parse_qsl(parts.query, keep_blank_values=True)
        ]
    )
    return urlunsplit((parts.scheme, netloc, parts.path, query, ""))


def redact(value):
    if isinstance(value, dict):
        return {
            key: "[redacted]"
            if key.lower() in SECRET_QUERY_KEYS
            else item
            if key == "transcript_hash"
            else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if not isinstance(value, str):
        return value
    value = URL.sub(lambda match: redact_url(match.group()), value)
    value = SECRET_LABEL.sub(
        lambda match: match.group(1) + ": [redacted]", value
    )
    value = re.sub(r"\b[A-Fa-f0-9]{32,}\b", "[redacted]", value)
    value = re.sub(r"\b(?:fckb_|lb_ak_)[A-Za-z0-9_-]+", "[redacted]", value)
    return re.sub(
        r"(?i)\b(PIN|verification code)\s+\d{4,8}\b", r"\1 [redacted]", value
    )


def parse_when(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("timestamps must include a timezone")
    return result.astimezone(UTC)


def window(day, timezone, cutoff):
    zone = ZoneInfo(timezone)
    selected = date.fromisoformat(day)
    start = datetime.combine(selected, time.min, zone).astimezone(UTC)
    end = datetime.combine(
        selected + timedelta(days=1), time.min, zone
    ).astimezone(UTC)
    upper = min(end, parse_when(cutoff))
    if upper <= start:
        raise ValueError("the selected day has not started at the cutoff")
    return {
        "date": day,
        "timezone": timezone,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "cutoff": upper.isoformat(),
    }


class PlainHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1
        elif tag in {"p", "div", "br", "li", "tr"}:
            self.text.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden:
            self.text.append(data)


def mime_parts(payload, kind):
    found = []
    if payload.get("mime_type", payload.get("mimeType")) == kind:
        body = payload.get("body") or {}
        content = body.get("content")
        encoded = body.get("base64_url_content", body.get("data"))
        if content is not None:
            found.append(content)
        elif encoded:
            decoded = base64.urlsafe_b64decode(
                encoded + "=" * (-len(encoded) % 4)
            )
            found.append(decoded.decode("utf-8", errors="replace"))
    for part in payload.get("parts") or []:
        found.extend(mime_parts(part, kind))
    return found


def gmail_messages(response):
    if response.get("isError") or response.get("is_error"):
        raise ValueError("Gmail connector returned an error")
    response = response.get("structuredContent", response)
    if "responses" in response:
        for thread in response["responses"]:
            if thread.get("isError") or thread.get("error"):
                raise ValueError("Gmail thread response is incomplete")
            yield from thread.get("messages") or []
    elif "messages" in response:
        yield from response["messages"]
    elif "message" in response:
        yield response["message"]
    elif "payload" in response:
        yield response
    else:
        raise ValueError(
            "expected Gmail full messages or threads, not search snippets"
        )


def normalize_gmail(response, bounds, person):
    rows = []
    for message in gmail_messages(response):
        payload = message.get("payload") or {}
        if not payload:
            raise ValueError("Gmail message has no full payload")
        headers = {
            h["name"].lower(): h["value"] for h in payload.get("headers") or []
        }
        stamp = message.get("internal_date", message.get("internalDate"))
        if stamp is None:
            raise ValueError("Gmail message has no internal timestamp")
        at = datetime.fromtimestamp(int(stamp) / 1000, UTC)
        if at >= parse_when(bounds["cutoff"]):
            continue
        text = mime_parts(payload, "text/plain")
        if not text:
            parser = PlainHTML()
            parser.feed("\n".join(mime_parts(payload, "text/html")))
            text = ["".join(parser.text)]
        labels = message.get("label_ids", message.get("labelIds", []))
        actor = [
            email.lower()
            for _, email in getaddresses([headers.get("from", "")])
        ]
        rows.append(
            redact(
                {
                    "source_type": "gmail",
                    "id": message["id"],
                    "thread_id": message.get(
                        "thread_id", message.get("threadId")
                    ),
                    "timestamp": at.isoformat(),
                    "in_window": at >= parse_when(bounds["start"]),
                    "title": headers.get("subject", ""),
                    "from": headers.get("from"),
                    "to": headers.get("to"),
                    "rfc822_message_id": headers.get("message-id"),
                    "actor_match": person.lower() in actor,
                    "is_draft": "DRAFT" in labels,
                    "text": "\n".join(text),
                    "has_full_text": bool(any(text)),
                }
            )
        )
    return rows


def deduplicate(rows):
    kept, positions = [], {}
    for row in rows:
        source = row["source_type"]
        key = (source, str(row["id"]))
        if source in {"email", "gmail"} and row.get("rfc822_message_id"):
            key = ("mail", row["rfc822_message_id"])
        if source == "call":
            key = (source, row.get("dialpad_call_id") or row["id"])
            fingerprint = row.get("transcript_hash")
            if fingerprint:
                at = parse_when(row["timestamp"])
                twin = next(
                    (
                        index
                        for index, item in enumerate(kept)
                        if item["source_type"] == "call"
                        and item.get("transcript_hash") == fingerprint
                        and item.get("operator_email")
                        == row.get("operator_email")
                        and item.get("contact_id") == row.get("contact_id")
                        and abs(
                            (at - parse_when(item["timestamp"])).total_seconds()
                        )
                        <= 5
                    ),
                    None,
                )
                if twin is not None:
                    kept[twin].setdefault("duplicate_ids", []).append(row["id"])
                    continue
        if key in positions:
            original = kept[positions[key]]
            if row.get("has_full_text") and not original.get("has_full_text"):
                row.setdefault("duplicate_ids", []).extend(
                    [original["id"], *original.get("duplicate_ids", [])]
                )
                kept[positions[key]] = row
            else:
                original.setdefault("duplicate_ids", []).append(row["id"])
            continue
        positions[key] = len(kept)
        kept.append(row)
    return kept


def sql_literal(value):
    return "'" + str(value).replace("'", "''") + "'"


ACTIVITY_SOURCES = {
    "call": "call",
    "sms": "sms",
    "email": "email",
    "chat": "chat",
    "task": "task",
    "calendar_event": "calendar_event",
    "linear_local": "linear_action",
}
# chat and linear_local stay unfiltered: other people's messages and Linear
# actions are context the report needs; timeline.py matches the actor itself.
STAFF_SOURCES = {"call", "sms", "email", "calendar_event"}
OPS_SOURCES = (*ACTIVITY_SOURCES, "issue_category")
ACTIVITY_FIELDS = {
    "call": ["dialpad_call_id", "operator_email", "direction", "state", "duration_seconds", "connected_at", "ended_at", "snippet", "has_transcript"],
    "sms": ["direction", "snippet", "line_email"],
    "email": ["rfc822_message_id", "thread_id", "title", "from_addr", "to_addr", "mailbox", "direction", "event_type", "snippet"],
    "chat": ["sender_email", "channel_id", "snippet"],
    "task": ["fc_task_id", "workflow_name", "status_name", "completed_at"],
    "calendar_event": ["end", "title", "calendar", "organizer_email", "status", "meet_link"],
    "linear_local": ["actor", "kind", "linear_identifier", "snippet"],
}
ISSUE_CATEGORY_QUERY = "SELECT l.id, l.last_synced_at AS timestamp, l.issue_identifier AS identifier, l.fc_task_id::text AS fc_task_id, coalesce(nullif(l.category,''), i.category) AS category FROM ops_linearissuelink l LEFT JOIN ops_issue i ON i.id=l.issue_fk_id WHERE coalesce(nullif(l.category,''), i.category) IS NOT NULL UNION ALL SELECT -t.id, t.synced_at, NULL, t.fc_task_id, i.category FROM fc_tasks t JOIN ops_issue i ON i.id=t.issue_id WHERE i.category IS NOT NULL"


def pipeline_category(source_match):
    return (
        "(SELECT coalesce(p.payload->'case_definition'->>'category', i.category) AS category"
        " FROM ops_decisionsource s JOIN ops_decisionproposal p ON p.source_id=s.id"
        " LEFT JOIN ops_issue i ON i.id::text=p.issue_id"
        f" WHERE {source_match}"
        " AND coalesce(p.payload->'case_definition'->>'category', i.category) IS NOT NULL"
        " GROUP BY 1 ORDER BY count(*) DESC, 1 LIMIT 1)"
    )


SMS_THREAD_MATCH = (
    "s.source_ref LIKE 'sms-thread:%' AND x.id BETWEEN"
    " split_part(split_part(s.source_ref,':',3),'-',1)::bigint AND"
    " split_part(split_part(s.source_ref,':',3),'-',2)::bigint"
)
ENRICHMENT = {
    "call": ("calls", "CASE WHEN length(coalesce(x.transcript,''))>0 THEN md5(x.transcript) END AS transcript_hash, " + pipeline_category("s.source_ref='call:'||x.id") + " AS pipeline_category"),
    "sms": ("sms", pipeline_category(SMS_THREAD_MATCH) + " AS pipeline_category"),
    "email": ("emails", "x.message_id, " + pipeline_category("s.source_ref='email:'||x.id") + " AS pipeline_category"),
    "task": ("fc_tasks", "x.synced_at"),
    "calendar_event": ("calendar_events", "x.attendees, x.synced_at"),
    "linear_local": ("ops_linearhumanaction", "x.linear_issue_id"),
}


def enrichment_query(source, ids):
    """Columns the kb activity feed does not carry, by row id."""
    table, columns = ENRICHMENT[source]
    wanted = ", ".join(str(int(identity)) for identity in ids)
    return f"SELECT x.id, {columns} FROM {table} x WHERE x.id IN ({wanted})"


def activity_arguments(source, bounds, person):
    """kb `activity` bounds are inclusive: ending one microsecond early keeps
    the exclusive `< cutoff` (calendar: `< day end`) of the day window."""
    end = bounds["end"] if source == "calendar_event" else bounds["cutoff"]
    arguments = {
        "since": bounds["start"],
        "until": (parse_when(end) - timedelta(microseconds=1)).isoformat(),
        "source_types": [ACTIVITY_SOURCES[source]],
    }
    if source in STAFF_SOURCES:
        arguments["staff"] = person
    return arguments


def activity_row(source, item, bounds, snippet_chars):
    if source == "calendar_event" and (
        parse_when(item["end"]) <= parse_when(bounds["start"])
        if item.get("end")
        else parse_when(item["timestamp"]) < parse_when(bounds["start"])
    ):
        return None
    identity = str(item["id"])
    row = {
        "id": int(identity) if identity.isdigit() else identity,
        "timestamp": item["timestamp"],
    }
    if source not in {"calendar_event", "linear_local"}:
        company = item.get("company") or {}
        row |= {"company_id": company.get("id"), "company": company.get("name")}
    if source not in {"task", "calendar_event", "linear_local"}:
        row["contact_id"] = (item.get("contact") or {}).get("id")
    row |= {name: item.get(name) for name in ACTIVITY_FIELDS[source]}
    if source == "task":
        row["title"] = item.get("name")
    if source == "email":
        row["is_draft"] = False
    if "snippet" in row:
        row["snippet"] = (row["snippet"] or "")[: int(snippet_chars)]
    row["links"] = item.get("links") or {}
    return row
