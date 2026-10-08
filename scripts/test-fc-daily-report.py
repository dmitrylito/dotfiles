"""Fixture checks for the global fc-daily-report evidence command.

Usage: uv run --with pytest python -m pytest -q scripts/test-fc-daily-report.py
Requires Python 3.11+ and pytest; mocks source access and never mutates live data.
"""

import importlib.util
import json
from datetime import timedelta
from pathlib import Path

import pytest

SCRIPTS = (
    Path(__file__).resolve().parents[1] / "dot_local/libexec/fc-daily-report"
)


@pytest.fixture
def collector(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(
        "daily_report_collector", SCRIPTS / "collect.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def bounds(collector):
    return collector.window(
        "2026-10-05", "America/New_York", "2026-10-05T21:00:00Z"
    )


def test_local_days_follow_dst_and_reject_naive_cutoffs(collector):
    spring = collector.window(
        "2026-03-08", "America/New_York", "2026-03-10T00:00:00Z"
    )
    fall = collector.window(
        "2026-11-01", "America/New_York", "2026-11-03T00:00:00Z"
    )
    assert collector.parse_when(spring["end"]) - collector.parse_when(
        spring["start"]
    ) == timedelta(hours=23)
    assert collector.parse_when(fall["end"]) - collector.parse_when(
        fall["start"]
    ) == timedelta(hours=25)
    with pytest.raises(ValueError, match="timezone"):
        collector.window(
            "2026-10-05", "America/New_York", "2026-10-05T21:00:00"
        )


def message(payload, stamp="1791220000000", identity="mail1"):
    return {"id": identity, "internal_date": stamp, "payload": payload}


def test_connector_mime_content_and_raw_gmail_encoding(collector, bounds):
    import base64

    payload = {
        "mime_type": "multipart/mixed",
        "headers": [
            {"name": "From", "value": "Dmitry <dmitrylitoshik@fleetchaser.com>"}
        ],
        "parts": [
            {
                "mime_type": "multipart/alternative",
                "parts": [
                    {
                        "mime_type": "text/plain",
                        "body": {
                            "content": "API key: abcdefabcdefabcdefabcdefabcdefabcdef"
                        },
                    },
                    {
                        "mime_type": "text/html",
                        "body": {"content": "<p>wrong alternative</p>"},
                    },
                ],
            },
        ],
    }
    raw = {
        "mimeType": "text/plain",
        "body": {
            "data": base64.urlsafe_b64encode(
                "Customer confirmed café works".encode()
            )
            .decode()
            .rstrip("=")
        },
    }
    result = collector.normalize_gmail(
        {
            "structuredContent": {
                "responses": [
                    {
                        "messages": [
                            message(payload),
                            message(raw, identity="mail2"),
                        ]
                    }
                ]
            }
        },
        bounds,
        "dmitrylitoshik@fleetchaser.com",
    )
    assert result[0]["actor_match"] is True
    assert result[0]["text"] == "API key: [redacted]"
    assert result[1]["text"] == "Customer confirmed café works"
    assert all(row["has_full_text"] for row in result)


def test_html_fallback_context_and_boundary_are_honest(collector, bounds):
    payload = {
        "mime_type": "text/html",
        "body": {
            "content": "<style>hidden</style><p>Hello &amp; welcome</p><script>hidden</script>"
        },
    }
    rows = collector.normalize_gmail(
        {
            "messages": [
                message(payload, "1791100000000", "context"),
                message(
                    payload,
                    str(
                        int(
                            collector.parse_when(bounds["cutoff"]).timestamp()
                            * 1000
                        )
                    ),
                    "boundary",
                ),
            ]
        },
        bounds,
        "dmitrylitoshik@fleetchaser.com",
    )
    assert len(rows) == 1
    assert rows[0]["in_window"] is False
    assert rows[0]["text"].strip() == "Hello & welcome"
    with pytest.raises(ValueError, match="full messages"):
        collector.normalize_gmail(
            {"emails": [{"snippet": "not evidence"}]},
            bounds,
            "dmitrylitoshik@fleetchaser.com",
        )


def test_redaction_keeps_safe_fingerprints_and_removes_access_links(collector):
    hashed = "a" * 32
    raw = {
        "transcript_hash": hashed,
        "text": "API key for their account:\n"
        + hashed
        + "\nhttps://app.example/cloud-browser/public/lb_ak_abcdef\nhttps://user:pass@example.test/path?token=abc&x=ok\nPIN 123456",
        "access_token": "opaque",
    }
    result = collector.redact(raw)
    assert result["transcript_hash"] == hashed
    assert hashed not in result["text"]
    assert "lb_ak_" not in result["text"]
    assert "user:pass" not in result["text"]
    assert "token=abc" not in result["text"]
    assert "123456" not in result["text"]
    assert result["access_token"] == "[redacted]"


def test_duplicate_call_legs_not_separate_calls_and_later_calls_survive(
    collector,
):
    row = {
        "source_type": "call",
        "id": 1,
        "timestamp": "2026-10-05T14:00:00Z",
        "transcript_hash": "same",
        "operator_email": "dmitry",
        "contact_id": 1,
    }
    rows = collector.deduplicate(
        [
            row,
            {**row, "id": 2, "timestamp": "2026-10-05T14:00:01Z"},
            {**row, "id": 3, "timestamp": "2026-10-05T15:00:00Z"},
            {**row, "id": 4, "operator_email": "andrey"},
        ]
    )
    assert [r["id"] for r in rows] == [1, 3, 4]
    assert rows[0]["duplicate_ids"] == [2]


def test_full_gmail_replaces_mirror_summary_and_other_authors_remain_context(
    collector, bounds
):
    sources = {
        "emails": {
            "rows": [
                {
                    "source_type": "email",
                    "id": 1,
                    "timestamp": "2026-10-05T14:00:00Z",
                    "rfc822_message_id": "same",
                    "from_addr": "Another <andrey@fleetchaser.com>",
                    "snippet": "summary",
                },
                {
                    "source_type": "gmail",
                    "id": 2,
                    "timestamp": "2026-10-05T14:00:00Z",
                    "rfc822_message_id": "same",
                    "has_full_text": True,
                    "text": "complete",
                    "actor_match": False,
                },
            ]
        }
    }
    rows = collector.activity_index(
        sources, "dmitrylitoshik@fleetchaser.com", bounds
    )
    assert len(rows) == 1
    assert rows[0]["text"] == "complete"
    assert rows[0]["actor_match"] is False


def test_clipped_sql_is_refused(collector):
    with pytest.raises(ValueError, match="clipped"):
        collector.sql_rows(
            {"columns": ["text"], "rows": [["partial"]], "cells_cut": 1}
        )


def test_pagination_preserves_partial_source_and_continues_others(
    collector, bounds
):
    class Reader:
        def call(self, tool, arguments):
            if tool == "describe_schema":
                return {}
            if "max(" in arguments["query"]:
                return {
                    "columns": ["latest"],
                    "rows": [["2026-10-05T20:00:00Z"]],
                }
            if "FROM calls" in arguments["query"]:
                return {
                    "columns": ["id", "timestamp"],
                    "rows": [[1, "2026-10-05T14:00:00Z"]],
                    "truncated_at_max_rows": True,
                }
            return {"columns": ["id", "timestamp"], "rows": []}

    result = collector.collect_ops_with(
        Reader(),
        bounds,
        "dmitry@example.com",
        {"snippet_chars": 100, "page_size": 10, "max_pages": 1},
    )
    assert result["call"]["status"] == "gap"
    assert len(result["call"]["rows"]) == 1
    assert result["sms"]["status"] == "collected"


def test_documents_cache_complete_pages_and_do_not_refetch(
    collector, tmp_path, monkeypatch
):
    config = {"max_pages": 3}
    collector.save(tmp_path / "manifest.json", {"config": config})
    calls = []

    class Reader:
        def call(self, tool, arguments):
            calls.append(arguments["offset"])
            return (
                {"text": "first", "next_offset": 5}
                if arguments["offset"] == 0
                else {"text": "second"}
            )

    monkeypatch.setattr(collector, "transport", lambda config: Reader())
    from argparse import Namespace

    args = Namespace(run=str(tmp_path), ref=["call:1"], refresh=False)
    assert collector.documents(args)["fetched"] == 1
    assert collector.documents(args)["fetched"] == 0
    assert calls == [0, 5]
    assert (
        json.loads((tmp_path / "documents.json").read_text())["call:1"]["text"]
        == "firstsecond"
    )


def test_failed_page_never_caches_partial_document(
    collector, tmp_path, monkeypatch
):
    collector.save(tmp_path / "manifest.json", {"config": {"max_pages": 2}})

    class Reader:
        def call(self, tool, arguments):
            if arguments["offset"]:
                raise ValueError("remote unavailable")
            return {"text": "partial", "next_offset": 5}

    monkeypatch.setattr(collector, "transport", lambda config: Reader())
    from argparse import Namespace

    with pytest.raises(ValueError, match="unavailable"):
        collector.documents(
            Namespace(run=str(tmp_path), ref=["call:1"], refresh=False)
        )
    assert not (tmp_path / "documents.json").exists()


def test_mcp_initialization_and_read_tools_use_existing_token(
    collector, monkeypatch
):
    requests = []

    class Reply:
        def __init__(self, payload):
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self, limit):
            return json.dumps(self.payload).encode()

    class Opener:
        def open(self, request, timeout):
            body = json.loads(request.data)
            requests.append((body, dict(request.header_items())))
            if body["method"] == "initialize":
                return Reply(
                    {
                        "id": body["id"],
                        "result": {"protocolVersion": "2025-11-25"},
                    }
                )
            if body["method"] == "notifications/initialized":
                return Reply({})
            return Reply(
                {
                    "id": body["id"],
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": '{"columns":["id"],"rows":[[1]]}',
                            }
                        ]
                    },
                }
            )

    monkeypatch.setenv("OPS_CENTER_MCP_TOKEN", "existing-key")
    monkeypatch.setattr(collector, "build_opener", lambda *args: Opener())
    client = collector.MCPTransport(
        {
            "mcp_url": "https://ops.example/mcp",
            "timeout_seconds": 2,
            "max_response_bytes": 10000,
        }
    )
    assert client.call("run_sql", {"query": "SELECT 1"})["rows"] == [[1]]
    assert [r[0]["method"] for r in requests] == [
        "initialize",
        "notifications/initialized",
        "tools/call",
    ]
    assert requests[-1][1]["Mcp-protocol-version"] == "2025-11-25"
    with pytest.raises(ValueError, match="unsupported"):
        client.call("mutate", {})


def test_mcp_refuses_token_in_url_and_redirects(collector, monkeypatch):
    monkeypatch.setenv("OPS_CENTER_MCP_TOKEN", "existing-key")
    with pytest.raises(ValueError, match="environment"):
        collector.MCPTransport(
            {"mcp_url": "https://user:secret@ops.example/mcp"}
        )
    with pytest.raises(ValueError, match="redirects"):
        collector.NoRedirect().redirect_request(
            None, None, 302, None, None, "https://other.example"
        )


def test_reusing_run_never_launches_remote_reads(
    collector, tmp_path, monkeypatch, bounds
):
    from argparse import Namespace

    collector.save(
        tmp_path / "manifest.json",
        {
            "person": "dmitry",
            "mode": "timeline",
            "bounds": bounds,
            "config": {"timeline_bucket_minutes": 30},
        },
    )
    collector.save(
        tmp_path / "sources.json",
        {"calls": {"status": "collected", "rows": []}},
    )
    monkeypatch.setattr(
        collector,
        "transport",
        lambda *args: pytest.fail("unexpected remote read"),
    )
    assert (
        collector.collect(Namespace(run=str(tmp_path), refresh=False))["mode"]
        == "timeline"
    )


def test_mcp_string_result_wrapper(collector, monkeypatch):
    monkeypatch.setenv("OPS_CENTER_MCP_TOKEN", "existing-key")
    monkeypatch.setattr(
        collector.MCPTransport,
        "post",
        lambda self, method, params, notification=False: (
            {"protocolVersion": "2025-11-25"}
            if method == "initialize"
            else {
                "structuredContent": {
                    "result": '{"columns":["id"],"rows":[[1]]}'
                },
                "isError": False,
            }
        ),
    )
    assert collector.MCPTransport({"mcp_url": "https://ops.example/mcp"}).call(
        "run_sql", {"query": "SELECT 1"}
    )["rows"] == [[1]]


def test_managed_secret_fallback_and_env_override(
    collector, tmp_path, monkeypatch
):
    monkeypatch.delenv("OPS_CENTER_MCP_TOKEN", raising=False)
    monkeypatch.delenv("OPS_CENTER_MCP_API_KEY", raising=False)
    monkeypatch.setattr(collector.Path, "home", lambda: tmp_path)
    path = tmp_path / ".config/secrets/shared.env"
    path.parent.mkdir(parents=True)
    path.write_text(
        "export OTHER_SECRET=no\nexport OPS_CENTER_MCP_API_KEY='fixture-key'\n"
    )
    assert collector.mcp_token() == "fixture-key"
    monkeypatch.setenv("OPS_CENTER_MCP_API_KEY", "override")
    assert collector.mcp_token() == "override"


def test_global_helpers_are_python_311_compatible():
    import ast

    for path in SCRIPTS.glob("*.py"):
        ast.parse(path.read_text(), filename=str(path), feature_version=(3, 11))


def at(hour, minute=0):
    from datetime import UTC, datetime

    return datetime(2026, 10, 5, hour, minute, tzinfo=UTC).timestamp()


def iso(hour, minute=0):
    from datetime import UTC, datetime

    return datetime(2026, 10, 5, hour, minute, tzinfo=UTC).isoformat()


@pytest.fixture
def timeline_module(collector):
    import timeline

    return timeline


def test_timeline_measures_sessions_calls_and_tasks(
    collector, timeline_module, tmp_path, bounds
):
    def span(start, end, cls, title, url=None, profile="Work"):
        return {
            "start": start,
            "end": end,
            "class": cls,
            "title": title,
            "url": url,
            "profile": profile,
        }

    console = (
        "https://console.fleetchaser.com/tasks/kanban/1?dialog=task&taskId=42"
    )
    collector.save(
        tmp_path / "manifest.json",
        {
            "bounds": bounds,
            "config": {"timeline_bucket_minutes": 30},
        },
    )
    collector.save(
        tmp_path / "screen.json",
        {
            "host": "fcoffice",
            "spans": [
                span(
                    at(13), at(13, 10), "com.mitchellh.ghostty", "DLCO-1: ops"
                ),
                span(
                    at(14),
                    at(14, 30),
                    "chromium",
                    "Meet - abc-defg-hij - Chromium",
                ),
                span(
                    at(15, 2),
                    at(15, 6),
                    "chromium",
                    "(2) Fleet Chaser",
                    console,
                ),
                span(
                    at(16),
                    at(16, 5),
                    "chromium",
                    "News",
                    "https://x.test/",
                    "Personal",
                ),
            ],
            "calls": [
                {"start": at(14), "end": at(14, 30), "apps": ["chromium"]},
                {"start": at(15), "end": at(15, 10), "apps": ["chromium"]},
            ],
            "panes": [
                {
                    "start": at(13),
                    "end": at(13, 5),
                    "host": "dlco-1",
                    "pane": "w1:p1",
                    "agent": "claude",
                    "agent_session": "s1",
                    "title": "billing fix",
                }
            ],
        },
    )
    collector.save(
        tmp_path / "agents.json",
        {
            "sessions": [
                {
                    "agent": "claude",
                    "host": "DLCO-1",
                    "session_id": "s1",
                    "title": "billing fix",
                    "cwd": "/p/backend",
                    "prompts": [{"at": at(12, 59), "text": "fix billing"}],
                    "active": [[at(12, 59), at(13, 20)]],
                },
                {
                    "agent": "codex",
                    "host": "DLCO-1",
                    "session_id": "s2",
                    "title": "ops report",
                    "cwd": "/p/ops-center",
                    "prompts": [{"at": at(13, 7), "text": "report"}],
                    "active": [[at(13, 7), at(13, 9)]],
                },
            ]
        },
    )
    dialpad = {
        "source_type": "call",
        "id": 1,
        "dialpad_call_id": "dp1",
        "company": "Paragon",
        "timestamp": iso(15),
        "connected_at": iso(15),
        "ended_at": iso(15, 10),
    }
    collector.save(
        tmp_path / "sources.json",
        {
            "call": {"rows": [dialpad, dialpad | {"id": 2}]},
            "calendar_event": {
                "rows": [
                    {
                        "source_type": "calendar_event",
                        "id": 7,
                        "title": "Sync",
                        "timestamp": iso(14),
                        "end": iso(14, 30),
                        "meet_link": "https://meet.google.com/abc-defg-hij",
                    },
                    {
                        "source_type": "calendar_event",
                        "id": 8,
                        "title": "Site visit",
                        "timestamp": iso(17),
                        "end": iso(18),
                    },
                ]
            },
            "task_audit": {
                "rows": [
                    {
                        "source_type": "task_audit",
                        "id": "a1",
                        "task_id": "42",
                        "title": "INST: Paragon",
                        "action": "t:u",
                        "timestamp": iso(15, 5),
                    }
                ]
            },
        },
    )
    rules = tmp_path / "rules.json"
    rules.write_text(
        json.dumps(
            {
                "rules": {
                    "profile:Work": "work",
                    "profile:Personal": "personal",
                    "project:backend": "work",
                    "project:ops-center": "work",
                }
            }
        )
    )
    result = timeline_module.build(tmp_path, rules)

    sessions = {s["session_id"]: s for s in result["terminal"]["sessions"]}
    assert sessions["s1"]["focus_seconds"] == 7 * 60
    assert sessions["s2"]["focus_seconds"] == 3 * 60
    assert result["terminal"]["attribution_seconds"] == {
        "herdr": 300,
        "prompt-inferred": 300,
    }
    calls = result["calls"]
    assert [(c["kind"], round(c["seconds"])) for c in calls] == [
        ("meet", 1800),
        ("dialpad", 600),
    ]
    assert calls[0]["event"] == "Sync"
    assert calls[1]["during"][0] == {
        "label": "console.fleetchaser.com: Fleet Chaser",
        "seconds": 240,
    }
    assert [e["title"] for e in result["scheduled_meetings"]] == ["Site visit"]
    task = result["tasks"]["fc"][0]
    assert (
        task["fc_task_id"],
        task["screen_seconds"],
        len(task["actions"]),
    ) == (
        "42",
        240,
        1,
    )
    totals = result["totals"]
    assert totals["by_category"] == {
        "work": 2640,
        "personal": 300,
        "uncategorized": 7800,
    }
    assert totals["idle_seconds"] == 7800
    assert totals["calls_seconds"] == 2400
    assert totals["calls_off_screen_seconds"] == 360
    assert totals["work_seconds"] == 3000
    assert totals["scheduled_unmeasured_meeting_seconds"] == 3600
    assert [(r["type"], r["id"], r["seconds"]) for r in result["records"]] == [
        ("fc_task", "42", 240)
    ]
    assert timeline_module.build(tmp_path, None)["totals"]["by_category"] == {
        "uncategorized": 10740
    }


def test_idle_watching_locks_and_end_of_day_rules(
    collector, timeline_module, tmp_path, bounds
):
    from argparse import Namespace

    def span(start, end, cls, title, url=None):
        return {
            "start": start,
            "end": end,
            "class": cls,
            "title": title,
            "url": url,
            "profile": "Work",
        }

    collector.save(
        tmp_path / "manifest.json",
        {"bounds": bounds, "config": {"timeline_bucket_minutes": 30}},
    )
    collector.save(
        tmp_path / "screen.json",
        {
            "host": "fcoffice",
            "spans": [
                span(
                    at(13),
                    at(13, 10),
                    "chromium",
                    "Docs - Chromium",
                    "https://docs.google.com/document/d/abc/edit",
                ),
                span(at(13, 20), at(13, 30), "spotify", "Spotify"),
                span(
                    at(13, 35),
                    at(13, 40),
                    "chromium",
                    "Docs - Chromium",
                    "https://docs.google.com/document/d/abc/edit",
                ),
                span(
                    at(15),
                    at(15, 5),
                    "chromium",
                    "Docs - Chromium",
                    "https://docs.google.com/document/d/abc/edit",
                ),
            ],
            "locks": [{"start": at(13, 45), "end": at(14, 55)}],
            "idle": [
                {
                    "start": at(13, 10),
                    "end": at(13, 20),
                    "inhibitor_class": "chromium",
                    "inhibitor_title": "Training video - YouTube - Chromium",
                },
            ],
        },
    )
    result = timeline_module.build(tmp_path, None)
    totals = result["totals"]
    assert (
        totals["screen_seconds"],
        totals["watching_seconds"],
        totals["idle_seconds"],
    ) == (1800, 600, 900)
    assert [a["seconds"] for a in result["away"]] == [70 * 60]
    assert result["records"][0]["type"] == "google_doc"

    rules = tmp_path / "rules.json"
    outcome = collector.categorize(
        Namespace(
            run=str(tmp_path),
            categories=str(rules),
            day=False,
            work=["site:docs.google.com", "watching:chromium", "idle"],
            personal=["app:spotify"],
            set=[],
        )
    )
    assert outcome["totals"]["by_category"] == {"work": 2700, "personal": 600}
    assert outcome["still_uncategorized"] == []
    collector.categorize(
        Namespace(
            run=str(tmp_path),
            categories=str(rules),
            day=True,
            work=[],
            personal=[],
            set=["watching:Training video - YouTube=personal"],
        )
    )
    day = timeline_module.build(tmp_path, rules)["totals"]["by_category"]
    assert day == {"work": 2100, "personal": 1200}
    assert json.loads(rules.read_text())["rules"]["watching:chromium"] == "work"


def test_agent_sessions_keep_typed_prompts_only(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "agent_sessions", SCRIPTS / "agent_sessions.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module.Path, "home", lambda: tmp_path)
    claude = tmp_path / ".claude/projects/-p/abc.jsonl"
    claude.parent.mkdir(parents=True)
    claude.write_text(
        "\n".join(
            json.dumps(record)
            for record in [
                {"type": "ai-title", "aiTitle": "billing fix"},
                {
                    "type": "user",
                    "timestamp": iso(13),
                    "cwd": "/p",
                    "origin": {"kind": "human"},
                    "message": {"content": "fix the invoice"},
                },
                {
                    "type": "user",
                    "timestamp": iso(13, 1),
                    "message": {"content": [{"type": "tool_result"}]},
                },
                {
                    "type": "user",
                    "timestamp": iso(13, 2),
                    "origin": {"kind": "task-notification"},
                    "message": {"content": "agent finished"},
                },
                {"type": "assistant", "timestamp": iso(13, 3)},
            ]
        )
    )
    rollout = tmp_path / ".codex/sessions/2026/10/05/rollout-x.jsonl"
    rollout.parent.mkdir(parents=True)
    rollout.write_text(
        "\n".join(
            json.dumps(record)
            for record in [
                {
                    "type": "session_meta",
                    "payload": {
                        "id": "c1",
                        "cwd": "/ops",
                        "git": {"branch": "main"},
                    },
                },
                {
                    "type": "response_item",
                    "timestamp": iso(14),
                    "payload": {
                        "type": "message",
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": "# AGENTS.md instructions",
                            }
                        ],
                    },
                },
                {
                    "type": "response_item",
                    "timestamp": iso(14, 1),
                    "payload": {
                        "type": "message",
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": "log my day"}
                        ],
                    },
                },
            ]
        )
    )
    (tmp_path / ".codex/session_index.jsonl").write_text(
        json.dumps({"id": "c1", "thread_name": "daily log"})
    )
    start, end = at(0), at(23)
    [claude_session] = module.claude_sessions(start, end, 300)
    [codex_session] = module.codex_sessions(start, end, 300)
    assert [p["text"] for p in claude_session["prompts"]] == ["fix the invoice"]
    assert claude_session["title"] == "billing fix"
    assert claude_session["active"] == [[at(13), at(13, 3)]]
    assert [p["text"] for p in codex_session["prompts"]] == ["log my day"]
    assert (codex_session["title"], codex_session["branch"]) == (
        "daily log",
        "main",
    )


def test_this_machine_is_read_without_ssh(collector, monkeypatch):
    monkeypatch.setattr(collector.socket, "gethostname", lambda: "FCOFFICE")
    assert collector.is_local_host("fcoffice.chimera-pleco.ts.net")
    assert not collector.is_local_host("dlco-1.chimera-pleco.ts.net")
    with pytest.raises(ValueError, match="dash"):
        collector.ssh_command("-oProxyCommand=x", "true")


def test_fc_api_keeps_own_actions_inside_the_day(collector, bounds, tmp_path):
    import base64

    import fc_api

    def jwt(payload):
        body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
        return f"x.{body.rstrip('=')}.y"

    class FakeApi:
        def __init__(self):
            self.listed = []

        def access(self):
            return jwt({"employee_id": 7, "exp": 9999999999})

        def get(self, endpoint, params=None):
            assert endpoint == "tasks/workflow/1/"
            return {"statuses": [{"id": 3, "name": "Ready"}]}

        def pages(self, endpoint, params, page_size, max_pages):
            self.listed.append((endpoint, params.get("modified_date")))
            if endpoint == "tasks/task/":
                yield {
                    "id": 42,
                    "name": "INST: Paragon",
                    "displayNumber": 9,
                    "status": 3,
                    "workflow": {"id": 1, "name": "Installs"},
                }
                return
            yield from [
                {
                    "id": 3,
                    "created": iso(16),
                    "action": "t:u",
                    "createdBy": {"id": 7, "fullName": "Dmitry"},
                },
                {
                    "id": 2,
                    "created": iso(15),
                    "action": "t:m",
                    "createdBy": {"id": 8, "fullName": "Vlad"},
                },
                {
                    "id": 1,
                    "created": "2026-10-04T12:00:00Z",
                    "action": "t:c",
                    "createdBy": {"id": 7, "fullName": "Dmitry"},
                },
            ]

    api = FakeApi()
    result = fc_api.collect(
        bounds, {"timeout_seconds": 5, "page_size": 100, "max_pages": 3}, api
    )
    assert [d for e, d in api.listed if e == "tasks/task/"] == ["2026-10-05"]
    states = [r for r in result["rows"] if r["source_type"] == "fc_task_state"]
    actions = [r for r in result["rows"] if r["source_type"] == "task_audit"]
    assert states[0]["title"] == "9 - INST: Paragon"
    assert (states[0]["status"], states[0]["workflow"]) == ("Ready", "Installs")
    assert result["counts"] == {"tasks_modified": 1, "own_actions": 1}
    assert [(a["id"], a["action"]) for a in actions] == [("3", "t:u")]

    fc_api.set_refresh(jwt({"exp": 1}), tmp_path / "token.json")
    assert json.loads((tmp_path / "token.json").read_text())["access"] is None
    with pytest.raises(LookupError, match="fc-token"):
        fc_api.FCApi(path=tmp_path / "missing.json", login={})

    env = tmp_path / "fc-api.env"
    env.write_text(
        "# comment\nFC_EMAIL=d@fc.test\nFC_PASSWORD=p=ss word\n"
        "FC_CUSTOMER_ID=c1\nFC_HOST=https://fc.test\n"
    )
    login = fc_api.credentials(env)
    assert login["FC_PASSWORD"] == "p=ss word"
    calls = []

    def request(method, endpoint, params=None, body=None, token=None):
        calls.append((endpoint, body, token))
        if endpoint == "auth/login/":
            return {"access": "user-token"}
        return {
            "access": jwt({"employee_id": 7, "exp": 9999999999}),
            "refresh": "r",
        }

    api = fc_api.FCApi(path=tmp_path / "cache.json", login=login)
    api.request = request
    assert api.base == "https://fc.test/api/"
    assert claims_of(api.access())["employee_id"] == 7
    assert calls == [
        ("auth/login/", {"email": "d@fc.test", "password": "p=ss word"}, None),
        ("auth/token/", {"customerId": "c1"}, "user-token"),
    ]
    api.access()
    assert len(calls) == 2
    assert (tmp_path / "cache.json").stat().st_mode & 0o777 == 0o600


def claims_of(token):
    import fc_api

    return fc_api.claims(token)
