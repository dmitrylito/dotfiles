# Global daily-report evidence command

`fc-daily-report` is managed here, available from any working directory. The
daily-report skill (interpretation and report formatting) is installed globally from
`dot_agents/skills/fc-daily-report`, linked into `~/.claude/skills` and
`~/.codex/skills` on every machine. The team's copy lives in ops-center
(`.agents/skills/fc-daily-report`); keep the two in step when either changes. This
repository owns the executable, adapters and fixtures.

Sources: `dot_local/bin/executable_fc-daily-report` launches the standard-library
Python package in `dot_local/libexec/fc-daily-report/`. Targets are
`~/.local/bin/fc-daily-report` and `~/.local/libexec/fc-daily-report/`, installed on
all profiles and roles. No ops-center source command or new server endpoint is required.

```sh
fc-daily-report collect --date YYYY-MM-DD --mode timeline
fc-daily-report collect --date YYYY-MM-DD --mode work
fc-daily-report documents --run RUN_DIR --ref call:123 --ref email:456
fc-daily-report collect --date YYYY-MM-DD --run RUN_DIR
fc-daily-report collect --date YYYY-MM-DD --run RUN_DIR --refresh
fc-daily-report timeline --run RUN_DIR [--categories PATH]
fc-daily-report import-gmail --run RUN_DIR --input -
```

## Measured time (`timeline.json`)

Every collect also writes `timeline.json`, built offline from the run by
`timeline.py`. Inputs:

- `screen` — `window-time export` from `--screen-host` (default `fcoffice`, read
  locally when that is this machine): focused-window spans, desktop
  mic-in-use intervals, and the focused herdr pane with its Claude/Codex session.
- `agents` — `agent_sessions.py` run on each `--agent-hosts` machine (default
  `fcoffice` and `dlco-1.chimera-pleco.ts.net`, over SSH): session title, cwd,
  branch, typed prompts and active intervals from `~/.claude/projects` and
  `~/.codex/sessions`.
- Ops Center rows: Dialpad calls with `connected_at`/`ended_at`, calendar events
  with the Meet link, FC task audit (actor), live Linear history (actor).

Output: totals by category, `work_seconds` (work screen time ∪ calls), terminal
time per session (`herdr` when pane tracking covered it, else `prompt-inferred`:
the session last prompted on that host), calls with the screen activity during
each, call attempts, scheduled meetings that nothing measured, FC tasks and
Linear issues touched (actions plus on-screen seconds from `taskId=` and
`/issue/` URLs), chronological blocks and per-bucket summaries.

Call time comes from Dialpad, so calls on any device count. Meet time is measured
only when the desktop mic was in use, matched to the calendar event by the meeting
code in the Meet tab title; otherwise the event appears under
`scheduled_meetings`, not in totals. Screen idle over the omarchy shell plugin
timeout is excluded unless a call holds the mic.

Away is only time behind the omarchy lock screen: window-time polls the lock state
every five seconds (`locks`; `window-time import-locks` backfills from the shell
journal). Any other time without input (keyboard/mouse, two minutes, from the
omarchy shell plugin) is `idle`, whatever its length, or `watching` when a window
was holding the screen awake. Call time is never idle: calls keep counting through
idle from the desktop microphone, and Dialpad calls off the desktop are subtracted
from idle. Browser spans carry the active tab's exact URL from the window-time
Chromium extension (`url_source: tab`); older spans keep the History title match
(`history`). On console.fleetchaser.com the extension also reports the customer the
console is scoped to (the `customer_id` claim of its token; the token never leaves
the page), so a customer switch with the same URL starts a new span; names come from
the ops center's `mirror_fc_customer`, `fc_customers` totals time per customer, and
`fc_customer:<name>` is a rule key. `records` lists what was on screen by record: FC tasks, vehicles and
devices, admin objects, HubSpot records, Gmail threads, Google docs and Linear
issues.

Nothing is categorized automatically. Everything starts `uncategorized`; Dmitry
decides at the end of the day:

```sh
fc-daily-report review --run RUN_DIR --text        # groups, uncategorized first
fc-daily-report categorize --run RUN_DIR --work site:console.fleetchaser.com project:backend \
    --personal app:spotify --set 'watching:chromium=work'
fc-daily-report categorize --run RUN_DIR --day --personal 'page:www.google.com|g63 brabus - Google Search'
```

Keys, most specific first: `page:<site>|<title>`, `path:<site>/<first path segment>`, `session:<host>/<id>`,
`project:<cwd name>`, `site:<host>`, `profile:<Chromium profile>`,
`terminal:<host>`, `watching:<title>`, `watching:<class>`, `idle`,
`app:<class>`. Rules persist in `~/.config/fc-daily-report/categories.json`, so
later days start pre-sorted; `--day` writes the run's own `categories.json`,
which wins for that day only. `work_seconds` is work-categorized time plus calls.

Broad areas for the management report are a second rule set (`"areas"` in the same
files): `fc-daily-report categorize --run RUN_DIR --area --set 'site:dialpad.com=Customer
Support & Troubleshooting' [--day]`. Calls are keyed `call:<ref>`, `meet:<code>`,
`call_event:<title>` and `call_company:<name>`. `timeline.json` `areas` gives exclusive
time per area: a call owns its span, the rest goes to each segment's area, personal
time is excluded, and the areas sum to the tracked total.

FC tasks come from the FC backend API (`fc_api.py`): tasks modified on the day,
their current state (status names from each workflow), and the audit entries Dmitry
created that day, read at collect time (the audit log keeps every change with its
time, so no polling is needed). It logs in with the ops center's FC account (his
own), kept in the `fc-api` group of `.secrets.yaml.age` and rendered to
`~/.config/secrets/fc-api.env` on the work role; the token pair is cached in
`~/.local/state/fc-daily-report/fc-api.json` (0600). If the ops center's
`FC_PASSWORD` changes, update the group with `secrets-edit`. Without credentials,
`fc-daily-report fc-token --clipboard` stores a console refresh token instead.

The default MCP transport reads Ops Center remotely on every device. An existing
`OPS_CENTER_MCP_API_KEY` from the encrypted shared secrets page is read from the
environment or the private managed `~/.config/secrets/shared.env`; the optional
`OPS_CENTER_MCP_TOKEN` overrides it. `--transport docker` remains available.

The Docker transport uses the running `ops-backend` knowledge-base read services
with its SELECT-only role. The script is passed over stdin; the container stays on
its deployed checkout/image. Browser reads use existing SSH trust for `fcoffice`.
Live Linear is query-only and actor-attributed. Companion task audits verify the
`/app` mount and report stale development data explicitly rather than crediting
empty results. Collection does not sync, send, create, or alter source records.

`--transport mcp` uses the existing shared credential through HTTPS to
`https://ops.dlco.us/mcp`; tokens never belong in command arguments or artifacts.
The adapter implements the Ops Center server's stateless JSON Streamable HTTP
contract, not arbitrary SSE/stateful servers. It reuses `describe_schema`, `run_sql`,
and `get_document`. See the
[official transport specification](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports).
Codex's private global config includes `[mcp_servers.ops-center]` on every profile,
with the Authorization header rendered from that same encrypted secrets page. This
works for GUI, IDE, CLI and daemon instances without shell-environment dependence.
The modifier preserves unrelated live config and synchronizes this owned server.
New sessions pick up the connector; existing sessions are not interrupted.
[Official Codex MCP configuration](https://learn.chatgpt.com/docs/extend/mcp?surface=cli).

Sources needing a runtime (live Linear and task audit) use local Docker when
`ops-backend` is running, otherwise existing SSH trust for `--runtime-host`
(default `dlco-1.chimera-pleco.ts.net`; the bare `dlco` alias does not resolve to it on fcoffice).
Override that host if its alias differs; no SSH configuration or credentials are
created. Browser history independently uses `--browser-host fcoffice`. Failed SSH
sources remain gaps while remote Ops Center evidence remains available. A host that
is this machine is read locally, without SSH.

Gmail connector results pass through stdin before redacted persistence. Full
thread messages are normalized recursively from connector and native Gmail MIME
formats; HTML is a fallback. Selected threads are explicitly partial mailbox
coverage. Older messages remain context; only day-window activity enters the index.

Local private artifacts: `~/.local/state/ops-center/daily-reports/<day>/<run>/`.
A manifest freezes person, timezone, day bounds, cutoff and named limits. The index
contains previews and grouped browser pages; complete selected evidence is cached
separately. Reuse does no remote reads. Refresh keeps prior results, retries failed
sources and overlaps recent communication activity by five minutes; older backfills
need a new run. Gaps and stale sources remain visible. Browser visits and open-tab
spans never establish exact time spent or completed transactions.

Additional browser profiles must be selected explicitly after confirming ownership:
`--browser-profiles Default 'Profile 2' 'Profile 3'`. By default only the browser
account exactly matching `--person` is selected. Never include a coworker's profile.

Validation, from this source repository:

```sh
uv run --with pytest python -m pytest -q scripts/test-fc-daily-report.py
uv run --with ruff ruff check --isolated --select F,E9,I,B --target-version py311 --no-cache dot_local/libexec/fc-daily-report scripts/test-fc-daily-report.py
uv run --with ruff ruff format --isolated --line-length 80 --no-cache --check dot_local/libexec/fc-daily-report scripts/test-fc-daily-report.py
chezmoi apply --dry-run ~/.local/bin/fc-daily-report ~/.local/libexec/fc-daily-report
```

The fixtures cover timezone boundaries, Gmail formats and actor identity, credential
redaction, duplicate call legs, capped/failed pages, complete-document caching,
cache-only reuse, and MCP initialization/read-only dispatch. Live checks should use
read-only collection and inspect source gaps, not change synchronization or accounts.
