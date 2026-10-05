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


def source_queries(bounds, person, snippet_chars):
    lower, upper = (sql_literal(bounds[key]) for key in ["start", "cutoff"])
    who = sql_literal(person.lower())
    common = "x.id, x.timestamp, x.company_id, c.name AS company, x.contact_id"
    join = "LEFT JOIN companies c ON c.id=x.company_id"
    span = f"x.timestamp >= {lower} AND x.timestamp < {upper}"
    short = lambda field: f"left(coalesce({field},''), {int(snippet_chars)})"
    queries = {
        "call": f"SELECT {common}, x.dialpad_call_id, x.operator_email, x.direction, x.state, x.duration_seconds, {short('x.content_summary')} AS snippet, length(coalesce(x.transcript,''))>0 AS has_transcript, CASE WHEN length(coalesce(x.transcript,''))>0 THEN md5(x.transcript) END AS transcript_hash FROM calls x {join} WHERE {span} AND lower(x.operator_email)={who}",
        "sms": f"SELECT {common}, x.direction, {short('x.message_text')} AS snippet, x.raw_payload->'target'->>'email' AS line_email FROM sms x {join} WHERE {span} AND lower(x.raw_payload->'target'->>'email')={who}",
        "email": f"SELECT {common}, x.message_id, x.rfc822_message_id, x.thread_id, x.subject AS title, x.from_addr, x.to_addr, x.mailbox, x.direction, x.event_type, x.is_draft, {short('x.content_summary')} AS snippet FROM emails x {join} WHERE {span} AND (lower(x.mailbox)={who} OR lower(x.from_addr) LIKE '%' || {who} || '%') AND NOT x.is_draft",
        "chat": f"SELECT {common}, x.sender_email, x.channel_id, {short('x.message_text')} AS snippet FROM chat_messages x {join} WHERE {span}",
        "task": f"SELECT x.id, x.fc_modified_at AS timestamp, x.company_id, c.name AS company, x.fc_task_id, x.name AS title, x.workflow_name, x.status_name, x.completed_at, x.synced_at FROM fc_tasks x {join} WHERE x.fc_modified_at >= {lower} AND x.fc_modified_at < {upper} AND coalesce(x.workflow_name,'') NOT IN ('Marketing','Test','UC Test','111')",
        "calendar_event": f'SELECT x.id, x.start AS timestamp, x."end", x.summary AS title, x.calendar, x.organizer_email, x.attendees, x.status, x.synced_at FROM calendar_events x WHERE x.start < {sql_literal(bounds["end"])} AND (x."end" > {lower} OR (x."end" IS NULL AND x.start >= {lower})) AND (lower(x.calendar)={who} OR lower(x.organizer_email)={who} OR EXISTS(SELECT 1 FROM jsonb_array_elements(x.attendees) a WHERE lower(a->>\'email\')={who}))',
        "linear_local": f"SELECT x.id, x.occurred_at AS timestamp, x.linear_issue_id, x.actor, x.kind, {short('x.detail')} AS snippet FROM ops_linearhumanaction x WHERE x.occurred_at >= {lower} AND x.occurred_at < {upper}",
    }
    return queries
