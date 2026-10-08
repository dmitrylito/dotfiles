# Reusable daily evidence collector

Run the chezmoi-managed global command from any directory, using host Python 3.11+:

```bash
fc-daily-report collect --date YYYY-MM-DD --mode timeline
```

The default MCP path reads the existing remote Ops Center service, using the
chezmoi-managed shared `OPS_CENTER_MCP_API_KEY`. The credential comes from the
environment or private managed `~/.config/secrets/shared.env`, and the command is
installed on all device profiles/roles. `--transport docker` executes the existing deployed `kb.services.sql` reader in
`ops-backend`, with SELECT-only credentials and rolled-back read-only transactions.
The helper code travels over stdin: it does not require new code in the app image,
sync records, or repoint a shared container. Browser history uses the existing
read-only helper (locally on FCOffice, SSH elsewhere). Live Linear uses the deployed query-only client, complete
candidate/history pagination and explicit actors. Collection runs these independent
sources together; no model or scheduled job is involved.

The companion task audit is read in a separate read-only transaction after verifying
its `/app` mount against `--companion-checkout`. A stale local database stays labelled
`stale`, not an empty successful day; no database refresh is performed.

The JSON response shows the run directory, frozen bounds, source counts, gaps, and
index path. Read `index.json`, not `sources.json`, for discovery. Full relevant
source evidence is obtained with:

```bash
fc-daily-report documents --run RUN_DIR --ref call:123 --ref email:456
```

`documents.json` retains complete redacted text, including every MCP document page.
Existing documents are reused unless `--refresh` is explicit. A failed or capped
read does not persist the partial document as complete. Discovery and full evidence
are separate: never judge resolution from a short index snippet.

## Existing Ops Center MCP

When exposed to the agent, use the already-connected tools directly:
`describe_schema` for the relevant table, paginated `run_sql` for discovery, and
`get_document` for selected complete sources. `source_queries` in `~/.local/libexec/fc-daily-report/evidence.py`
defines the reviewed queries; use the same timezone/cutoff and pagination rules.
Company timelines supply sibling-contact follow-up when an outcome is unresolved.
Do not use semantic search as an exhaustive daily activity inventory.

For a single-command HTTP collection, use the existing shared credential; an
explicit `OPS_CENTER_MCP_TOKEN` can override it. Never print the key, put it in
command arguments, create a new key for this task, or change connector configuration.
The global Codex MCP entry is rendered from the same encrypted chezmoi secrets
page, including authentication for GUI/IDE/CLI/daemon sessions. Docker remains a supported alternative on this host. Live Linear and task audits
use local Docker when available, otherwise existing SSH trust for `--runtime-host`
(default `dlco-1.chimera-pleco.ts.net`); unavailable remote sources remain gaps.

The HTTP adapter targets this server's stateless JSON Streamable HTTP behavior. It
initializes and sends the negotiated protocol version, accepts only its read tools,
uses HTTPS except on localhost, and refuses redirects. It is not a general SSE or
stateful-session client. Protocol reference:
[official Streamable HTTP transport](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports).
The collector changes no MCP server endpoint or SDK dependency.

## Gmail completion

Database email is discovery and context, not proof of exhaustive live mailbox coverage.
Verify Gmail profile; search sent mail using the manifest's epoch boundaries;
paginate all search results; deduplicate candidate thread IDs and batch-read them
once. Check the connector's per-thread message limit and fetch omitted messages
before claiming the complete thread was read.

Pass the full connector response to the adapter through stdin, without printing or
saving the unredacted response:

```bash
fc-daily-report import-gmail --run RUN_DIR --input -
```

The adapter accepts `structuredContent.responses`, full thread `messages`, and
native full-message payloads. It handles nested plain-text bodies, connector
`content`/`base64_url_content`, native Gmail `data`, and HTML fallback. It preserves
older messages as context and marks the day window; future messages are excluded.
Search snippets are refused as full evidence. Full Gmail text supersedes a mirrored
email summary when the RFC Message-ID matches. Selected threads remain labelled
`selected_threads`; they never silently claim exhaustive mailbox coverage.

## Reuse and refresh

```bash
fc-daily-report collect --date YYYY-MM-DD --run RUN_DIR
fc-daily-report collect --date YYYY-MM-DD --run RUN_DIR --refresh
```

The first command reads the saved evidence only. Refresh advances the cutoff,
retains previous results, and merges new records by stable source IDs. Successful
communication reads use a configurable five-minute overlap; a failed source triggers
a full-day retry. Late historical backfills outside that overlap require a new run.
Browser history is reread as a day snapshot. Existing full documents are not refreshed
implicitly. Date, timezone and person must match the existing run.

A source failure remains a gap even if earlier data was retained. `collected` means
that source query was paginated successfully, not that its upstream synchronization
is exhaustive. Inspect `latest` and per-calendar sync timestamps before interpreting
absence. Task snapshots cannot establish who moved a card or its historical status;
use the companion task audit procedure in `sources.md` before claiming actor work.

## Browser identity and timing

By default only the browser profile whose account exactly matches `--person` is
selected. Profile names/account labels are retained for checking coverage. After
verifying ownership, add other profiles explicitly, for example:

```bash
fc-daily-report collect --date YYYY-MM-DD --mode timeline --browser-profiles Default 'Profile 2' 'Profile 3'
```

These directories were Dmitry's Personal/FC Tasks/FC Chat profiles on October 5,
2026; verify current labels before reuse. Never include another employee's profile.
Personal activity belongs only in a whole-day personal timeline, not a work report.

`browser_blocks` groups distinct pages with first/last visits in 30-minute windows;
it does not assign durations or infer uninterrupted work. Sparse windows and gaps
remain unknown. Full visited titles/paths are local evidence, not saved-action proof.

## Measured time

`collect` also reads FCOffice's `window-time` database (`--screen-host fcoffice`) and
Claude Code/Codex session logs on each `--agent-hosts` machine (default FCOffice and
DLCO-1), then writes `timeline.json` offline. Rebuild it without remote reads, for
example after editing the category rules:

```bash
fc-daily-report timeline --run RUN_DIR
```

What is measured: focused-window time on FCOffice; idle (no keyboard/mouse input
for two minutes, any length, "watching" when a window held the screen awake) and
away (only while the omarchy lock screen is up); the active tab's exact URL via the
window-time Chromium extension; the focused herdr pane and its agent session;
Dialpad connect-to-end for every call; FCOffice mic-in-use intervals matched to
calendar Meet links; and, through the FC backend API (logged in with the ops
center's FC account, kept in the chezmoi `fc-api` secrets group), tasks modified that
day with their current state and his own audit entries. What is not: work on other devices apart from Dialpad calls
(no MacBook tracker), meetings joined elsewhere (listed as `scheduled_meetings`),
and anything before each part existed (screen 2026-10-06; calls, panes, idle rows,
locks and exact URLs 2026-10-08; locks backfilled from the shell journal).

End-of-day categorization, never automatic:

```bash
fc-daily-report review --run RUN_DIR --text
fc-daily-report categorize --run RUN_DIR --work KEY... --personal KEY... [--set KEY=CATEGORY] [--day]
```

The chezmoi source `docs/fc-daily-report.md` documents fields and rule keys.

## Explicit limits and artifacts

Defaults: `--timeout-seconds 120`, `--max-response-bytes 8000000`, `--page-size 100`,
`--max-pages 100`, `--snippet-chars 240`, `--error-chars 1000`,
`--refresh-overlap-seconds 300`, `--timeline-bucket-minutes 30`, `--collector-workers 4`. There are no automatic
retries. The browser helper retains its explicit visit/snapshot limits. Timeouts,
page caps and clipped SQL cells become coverage gaps instead of empty successes.
These are source-collection limits, not hidden constraints on model output.

Artifacts live outside Git under `~/.local/state/ops-center/daily-reports/<date>/<run>/`:
`manifest.json`, `sources.json`, `index.json`, `screen.json`, `agents.json`,
`timeline.json`, and selected `documents.json`.
Directories/files are private (0700/0600), JSON replacements are atomic, and
redaction runs before output and persistence. Report/evidence/paste formats are
written from the same reviewed text after interpretation.

Fixture checks live in the chezmoi source: `uv run --with pytest python -m pytest -q scripts/test-fc-daily-report.py`.
