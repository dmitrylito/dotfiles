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
