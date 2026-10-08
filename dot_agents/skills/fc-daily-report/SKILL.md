---
name: fc-daily-report
description: Reconstruct Dmitry's day from measured screen time, Claude Code/Codex sessions, calls, texts, email, calendar, tasks, chat, Linear, and browser activity. Produce either a personal timeline of what occupied the day (with measured time totals) or a Fleet Chaser work report for posting. Reuse cached evidence for follow-ups.
---

# Fleet Chaser daily report

Choose the output from the user's intent: **timeline** for "what did I spend my
time on", "from when I started until now", or "for myself"; **management** for a
consolidated report with broad areas and time per area (for sending to
management); **work** for a daily report, work update, or report for posting. A bare "what did I do today" defaults
to a personal timeline, not a paste-ready company report. Run on demand; invoking
this skill does not create a schedule or send the report anywhere.

## Scope and evidence

- Default to today in `America/New_York`; honor an explicit date or yesterday.
  Today's report is through collection time. Use local midnight to next local
  midnight, converted to UTC, rather than a fixed 24-hour offset.
- Default person: Dmitry Litoshik, `dmitrylitoshik@fleetchaser.com`. Honor another
  explicitly requested person without attributing Dmitry's browser profile to them.
- Where an ops-center checkout exists (DLCO-1: `~/Projects/ops-center`), read its
  current `AGENTS.md` and communication/domain references; on other machines the
  collector and these references are enough, and Ops Center data comes through the
  collector's MCP transport or the connected Ops Center MCP tools.
  Start with [collector.md](references/collector.md), then consult the
  source-specific sections in [sources.md](references/sources.md) as needed; reuse
  instructions already read this session.
- Collect calls and transcripts, SMS, email, internal chat, calendar, FC task audit
  history, live Linear history, FCOffice browser visits, FCOffice measured screen time
  (`window-time`) and Claude Code/Codex sessions on FCOffice and DLCO-1. Session records
  show what engineering work was in progress but never replace the business sources.
- Read company-wide follow-up and task evidence when needed to establish an outcome.
  Evidence from a later day is follow-up, not an accomplishment on the report date.
- This is read-only source analysis. Do not sync/reconcile records, create tasks,
  change statuses, alter billing, publish mail, or change browser/SSH configuration.
  Save local report artifacts without putting raw customer data into Git.
- A missing source is a coverage limitation, not evidence of no activity. Continue
  with accessible sources and identify material gaps briefly.

## Collect once, read selectively

Use [collector.md](references/collector.md) first. The reusable command freezes the
local-day bounds/cutoff, batches read-only Ops Center queries, runs browser, screen,
agent-session and live Linear reads alongside them, normalizes evidence, and writes a
compact `index.json` plus the measured `timeline.json`.
It needs no server change or deployment. Use the existing Ops Center MCP's `run_sql`,
`describe_schema`, and `get_document` when connected; the local Docker path calls the
same read services. MCP never replaces browser history or a live actor audit.

- Start with counts, coverage, actor identities, source freshness and the index;
  do not print raw payloads or all browser visits. Discovery snippets are explicit
  previews, not sufficient evidence for outcomes.
- Fetch candidate full documents through `fc-daily-report documents`; it follows every
  text page and caches complete evidence. Read full relevant calls/threads and later
  same-day company replies before deciding whether troubleshooting succeeded.
- Verify Gmail profile, paginate sent search, deduplicate candidate thread IDs,
  batch-read once, and import through the tested Gmail adapter. It supports connector
  `body.content`/`base64_url_content` and native Gmail `body.data`, with recursive
  plain text and HTML fallback. Preserve older thread messages as context.
- Redact credentials and access links before printing or saving responses. Never
  write unredacted connector responses to temporary files. Retain safe full evidence
  locally; presentation limits must not silently become evidence truncation.
- Follow-up questions reuse `--run` without new remote reads. Use `--refresh` only
  for new activity, an explicit request, or a material stale/missing source; successful
  results survive source failures. The overlap covers recent arrivals, not every
  possible historical backfill. Start a new run when older source records changed.
- Missing transcripts, stale task audits, capped pages and unavailable sources stay
  coverage gaps. Use the source-specific fallback in [sources.md](references/sources.md)
  only for a material unresolved detail; do not restart successful collections.

## Interpret the day

Combine records by customer outcome or workstream, not by application or every
browser click. Distinguish completed outcomes, work progressed, and explicit
follow-ups. Credit team work as coordinated or reviewed unless Dmitry performed it.

Verify the actor behind calls and status changes. Count substantive conversations
separately from unanswered attempts, voicemail, transferred legs, and duplicates.
Calendar entries show scheduled events, not attendance. A visited editor, send screen,
cancellation URL, or installation form does not prove a saved change or delivery.
Customer acknowledgement, source readback, and actor-attributed task history provide
stronger outcome evidence. Do not count cancellation as completion or Bill as invoiced.

In **work** mode, include only Fleet Chaser work. Exclude Omada/network
administration, personal errands, unrelated projects, login flows, promotions, and random received emails. Include
relevant marketing email creation, support troubleshooting, field coordination,
billing, CRM work, and engineering/tooling that served Fleet Chaser. An inbound email
or alert alone is not work performed. Respect user-supplied absence/attendance details;
do not infer work hours from first/last visits or gaps, or repeat personal appointments
unless the user wants attendance in the report. Measured totals come only from
`timeline.json` (see Personal timeline).

## Company problems

Identify the few most consequential company/customer problems actually encountered:
customer-facing software defects, device reliability, installation/service delivery
failures, billing/cancellation errors, inaccurate customer data, missed customer
communications, or sales/account risks. Explain the concrete business impact and
whether the day's work resolved, mitigated, diagnosed, or left the problem open.

Do not substitute commentary about Dmitry's personal productivity, context switching,
too many tabs/tools, delegation, or being a bottleneck. A company process problem
belongs only when concrete evidence ties it to a customer or business failure.
Do not infer a root cause, frequency, or systemic trend from one day; describe
recurrence only when multiple independent examples or historical evidence support it.
Rank by evidenced customer/business impact and scope, not click volume. Group related
symptoms, avoid artificial issue quotas, and say when evidence supports no major issue.

## Output

Save reviewed text as `report.md` and a compact `evidence.md` in the collector's
private dated run directory. Evidence notes record source coverage, bounds/cutoff,
stable IDs/links, actor and outcome proof, and uncertainties. Preserve prior runs.
Do not invoke another model to summarize or check the same material.

### Personal timeline

Lead with the first observed work activity and collection cutoff. Then a **Time**
summary from `timeline.json` `totals`: work time (`work_seconds`: work-categorized
time plus calls), screen time by category, watching and idle time, away (locked)
time, terminal time, call time and how much of it was off-screen, and scheduled
meetings that nothing measured. These are measured on the FCOffice desktop and from Dialpad; say
so, and name `coverage` gaps (no screen data, no exact URLs, no idle rows, no pane
tracking, an unreachable agent host) instead of filling them.

**Categories are Dmitry's call.** Nothing is labelled work or personal
automatically. When `totals.uncategorized_seconds` is material, show the
`fc-daily-report review --run RUN --text` groups (largest uncategorized first,
with their pages and sessions), ask which are work and which personal, and record
the answers with `fc-daily-report categorize` (persistent rules by default,
`--day` for one-off pages). Report totals only after that, or label them
uncategorized. Never decide a category for him.

- **Calls**: one row per `calls` entry with who (company or calendar event), time and
  duration, and its `during` list: the work done while on that call belongs to the
  call. Dialpad durations cover any device. Meet time is measured only on FCOffice;
  `scheduled_meetings` are calendar time, not attendance, and stay out of totals.
- **Terminal**: `terminal.sessions` gives focus time per Claude/Codex session with its
  host, project, title and typed prompts. Use the prompts to say what each session was
  for. `prompt-inferred` attribution (before herdr pane tracking) is approximate; say so
  when it carries a material share.
- **Tasks and records touched**: `tasks.fc` and `tasks.linear` — Dmitry's own audited
  actions, on-screen time, and unattributed modifications kept separate — and
  `records` (time on FC vehicles/devices, admin objects, HubSpot records, Gmail
  threads, docs). Viewing is not changing. FC task actions come from the FC API
  (`fc_api` source), logged in with the ops center's FC account from the chezmoi
  `fc-api` secrets group; if it is a gap, report the error (an expired password
  means updating that group with `secrets-edit`) and say today's actions are missing.
- **Watching, idle and away**: away is time with the displays off or the screen
  locked (displays go off after five idle minutes). Any other
  time without keyboard/mouse input is `idle` (whatever its length) or `watching`
  when a window held the screen awake (video, Meet without a call). Call time is
  never idle. Present them as such; Dmitry categorizes idle and watching himself.
- **Timeline**: a chronological table from `buckets`/`blocks` with the concrete
  work/customer behind each window. Identify recurring workstreams and switches
  without judging productivity. Mark unexplained gaps instead of naming them lunch,
  breaks, or idle time; a calendar event in a gap may explain it as scheduled time.

Include substantial personal activity only when the user asks about their whole
day; keep it brief and avoid unnecessary personal details. Browser visit blocks in
`index.json` remain visits, not durations: never total them into hours; durations
come only from `timeline.json`.

### Management time report

Build it after categorization, from `timeline.json` `areas`: exclusive time per
broad area (each minute counted once; a call owns its whole span, so screen work
during a call counts toward the call's area; personal time is left out). Areas are
rules like categories: `fc-daily-report categorize --run RUN --area --set KEY=AREA`
(standing rules for sites, projects and apps; `--day` for individual calls
`call:call:<id>`, meetings `meet:<code>` / `call_event:<title>` and chat sessions).
Anything in `Unassigned` needs Dmitry's area before the report goes out; propose
areas from the evidence, he decides. Dmitry's areas (2026-10-08):
- **Support**: fixing hardware and coordinating fixes, support tickets in Linear.
- **Sales**: customer contact for adding vehicles, quotes, hardware drop-offs not
  tied to a fix, and customer questions about the product.
- **Billing**.
- **Internal Tools**: tooling, engineering and the ops pipeline.
- **Business Development**: internal meetings and product work (e.g. customer
  product feedback sessions), vendors, research.
- **Misc**: audio tools and music; its own row in the management report.

Title `Fleet Chaser Time Report — <date> (<start> – <cutoff>)`, the total, then one
row per area, largest first: area, time, share, and one line of concrete work done
(customers, outcomes, counts). End with open items. Save `report-management.md` and a
paste-ready `report-management.txt` (plain lines, `•` bullets) in the run directory.

### Work report for posting

Start with `Fleet Chaser Work Report — <date>` and add the cutoff for a partial day.
Use role-oriented sections suited to actual work: Support, Sales and Field
Coordination, Billing, Business Development, Management and Engineering. Omit empty
sections and recount each outcome once. Each section has exactly two sentence bullets
under its bold title, with a blank line before the list; consolidate sparse sections
instead of padding them. First person is appropriate for a report Dmitry will post.

End with **Biggest Company Issues**, one bullet per evidenced material business or
customer problem, naming impact and disposition. Skip this section in a personal
timeline unless requested. Detailed citations belong in `evidence.md`; keep the
paste-ready report clean. For terminal-to-Quill use, also save `report.txt` with plain
headings and literal `•` bullets and `report.html` for copying rendered rich text.
Verify files exist before linking them and put material coverage caveats outside the
paste-ready report.
