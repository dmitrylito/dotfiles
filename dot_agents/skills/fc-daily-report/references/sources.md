# Daily report source guide

These paths were verified on 2026-09-17. Check current model fields, runtime mounts,
access, and synchronization coverage before relying on them. Read the current
ops-center guide, including communication semantics, before interpreting records.

## Default entry point

Start with [collector.md](collector.md) and the reusable `fc-daily-report`
command. This guide supplies source-specific fallback and interpretation details;
do not reconstruct ad-hoc queries or repeat successful reads by default. The
Ops Center MCP's existing read tools supply discovery and full documents; direct
Docker collection uses those same services when the connector is unavailable.

## Collection procedure

The September 22, 2026 run exposed avoidable overhead from raw MIME/browser dumps,
repeated remote reads, and fetching missing transcripts only after drafting outcomes.
Use two passes: discover candidate workstreams, then read their complete evidence.

- Record local-day start/end and a fixed cutoff in the run directory; use the earlier
  of day end and cutoff for activity queries. Calendar overlap still uses day bounds
  and is only evidence of scheduled events. Record per-source collection times.
- Launch independent reads together: the browser helper, one read-only ops database
  collection, Gmail profile/sent search, and live Linear history. Verify the backend
  runtime and data freshness before its separate task-audit query. Use bounded tool
  waits for these foreground reads; do not introduce a scheduled job.
- Save database rows as JSONL with source tags. Initially print counts and a compact
  index of IDs, times, actors, company/contact names, subjects or summaries, and
  transcript availability. Inspect named columns/models only if a query needs them;
  do not dump entire model files or broad schema listings. Stop on SQL errors rather
  than treating an empty output file as success.
- Fetch missing transcripts for candidate substantive calls through the existing
  read client while reviewing the other indexes. Deduplicate mirrored call legs;
  duration alone does not establish substance. Read complete relevant transcripts
  and later same-day replies before assigning an outcome. A garbled transcript is a
  coverage limitation; corroborate it with written follow-up.
- From Gmail search results, deduplicate thread IDs and batch-read each needed thread
  once. Retain each response before printing a projection. For discovery show only
  message ID, timestamp, From/To, subject, and snippet; for interpretation extract the
  full `text/plain` MIME parts recursively, using HTML only if plain text is absent.
  Inspect individual messages to avoid repeated quoted chains without deleting new
  inline replies. Never print MIME headers, attachment encodings, or full HTML.
- When using `functions.exec`, `store(key, result.structuredContent)` retains a
  connector response for later projection via `load(key)` without refetching it.
  Persist needed evidence in the run directory before finishing; tool storage is not
  a durable artifact. Keep access codes and customer credentials out of projections
  and report artifacts, including browser titles and quoted replies.
- Reduce browser discovery to profile coverage and distinct relevant titles/paths
  with first/last visit times. Open detailed visits only to investigate a candidate
  action. A checkout or admin editor suggests a receipt/audit lookup, not completion.
- Fetch Linear candidate pages and histories once, saving full results locally;
  display only the requested person's in-window transitions grouped by issue, plus
  current state. Check pagination and GraphQL errors before reporting coverage.
- Follow up only on unresolved attribution, claimed outcomes, or missing material
  sources. Read at company scope where needed; do not rerun successful sources just
  because another one failed. Write report/evidence and paste formats from the same
  reviewed text, then verify their paths and nonempty contents.

## FCOffice browser history

`fcoffice` was reachable through SSH from `dlco`, as user `dmitrylito`, with six
Chromium profiles. The helper uses existing SSH trust and authentication; it neither
closes the browser nor changes its databases. It first tries read-only SQLite access.
For Chromium's exclusive locks, it copies the database and accompanying journals to
a temporary directory, checks source metadata stayed stable during copying, and runs
an integrity check on the copy. Temporary copies are removed after reading.
This fallback is explicitly labeled best-effort, not a transactional backup; use
history only as corroboration. See SQLite's [backup cautions](https://www.sqlite.org/howtocorrupt.html#backup_or_restore_while_a_transaction_is_active)
and Python's [SQLite interface](https://docs.python.org/3/library/sqlite3.html).

```bash
python3 ~/.local/libexec/fc-daily-report/browser_history.py --date YYYY-MM-DD --host fcoffice > <run-dir>/browser.json
```

The JSON includes profile identity labels, UTC and local visit times, title, sanitized
URL, coverage, and any per-profile failures. `--timezone` defaults to America/New_York.
`--timeout-seconds` bounds SSH to 60 seconds by default; there are no automatic retries.
`--max-visits` defaults to 20000 per profile, and incomplete coverage is explicit.
Use `--profile 'Default'` or repeated `--profile 'Profile 1'` to narrow a known profile.
Run `--local` only on the machine whose history is intended. Use `--browser-root`
to select another Chromium-compatible user-data directory on that machine.
`--snapshot-attempts` defaults to 3; changing files, failed integrity, and locked or
unreadable profiles are reported rather than silently interpreted as no visits.

Select profiles belonging to the requested person; do not conflate another employee's
profile with Dmitry. A workday can span the same person's personal and work profiles,
but retain only Fleet Chaser activity. Ignore restored-tab sweeps, redirects, and
auto-refreshes as independent work; cluster substantive visits with source records.
Do not calculate productive time from gaps between visits. Browser records are
corroboration and discovery clues, not transaction audit logs.

## Ops-center communications and Google Calendar

Main checkout (DLCO-1 only): `/home/dmitrylito/Projects/ops-center`. Deployed container:
`ops-backend`; database container: `ops-db`, database/user: `fcbot`.
Read-only database transactions avoid application-side signals and syncs:

```bash
docker exec -i ops-db psql -U fcbot -d fcbot -At <<'SQL'
BEGIN READ ONLY;
-- Select only the date window and required evidence fields here.
COMMIT;
SQL
```

Date predicates use `>= start` and `< end` with explicit UTC timestamps. Save verbose
results to the run directory and inspect manageable portions rather than truncated
tool output. `tools/fc.py` is the existing feed CLI; its `events` command requires
`--since/--until` because `--day/--range` are not forwarded for that command.

Models: `crm/models/comms.py`, `crm/models/fc.py`, `crm/models/identity.py`.

| Source/table | Fields and interpretation |
|---|---|
| `calls` | `timestamp`, `dialpad_call_id`, `operator_email`, direction/state/duration, `transcript`, `content_summary`, `action_items`, company/contact IDs. Verify speakers; shared or transferred calls can carry Dmitry's operator email while Andrey speaks. Retrieve missing transcripts through the existing Dialpad client when available; do not trigger ingestion. |
| `sms` | `timestamp`, `dialpad_message_id`, `direction`, `message_text`, company/contact IDs. `raw_payload.target.email` identifies the line; inspect sender identity on shared-line outbound messages. Reactions/MMS and repeated webhook rows are not substantive replies. |
| `emails` | `timestamp`, `mailbox`, `from_addr`, `to_addr`, `direction`, `thread_id`, `rfc822_message_id`, subject/body, `raw_payload`. Mailbox ownership does not establish authorship. Deduplicate messages mirrored through multiple mailboxes. |
| `chat_messages` | `timestamp`, `sender_email`, `sender_name`, channel, text, company/contact IDs. Collect the user's messages and enough surrounding context to establish responses/outcomes. |
| `calendar_events` | `start`, `end`, calendar, organizer, attendees, status, description, `synced_at`. Include events overlapping the day, not just events starting that day. Check coverage for both work and personal calendars; moved/deleted meetings may require invitation-email or conversation history. |
| `fc_tasks` | `fc_task_id`, display number, name, workflow/status, `completed_at`, `fc_modified_at`, description, `raw_payload`. Current snapshots identify candidates but do not establish who moved them or historical state. |

Join `contacts` and `companies` for names while preserving event-time company
attribution. Inspect all contacts at a company and relevant FC tasks before claiming
a customer request was unanswered. Staff are verified `@fleetchaser.com` identities;
`mirror_fc_employee` primarily describes customers' employees.

Calendar window: `start < window_end AND (end > window_start OR (end IS NULL AND
start >= window_start))`. Check per-calendar sync timestamps and treat a stale/missing
calendar as incomplete coverage, not an empty day.

## Gmail and other live sources

Use available Gmail connector tools to verify profile, search, and read relevant
threads. Use epoch-second `after:`/`before:` bounds derived from local-day endpoints
and verify boundary timestamps. Search sent mail and relevant inbound/meeting mail;
paginate completely. Automated messages in Sent are not authored work. Billing-system
emails and marketing sends may not appear in Gmail; use their own source records or
recipient acknowledgement. Never send, draft, label, or change mail for this report.

For HubSpot research, follow the installed HubSpot skill and read-only connector
guidance. Browser editor/schedule visits alone do not prove campaign sending. Inspect
actual campaign state only when needed to claim scheduled/sent status. Use existing
authenticated billing clients for readback when required; a cancellation page visit
alone does not prove cancellation.

## FC workboard audit trail

Companion checkout: `/home/dmitrylito/Projects/backend`; read its `AGENTS.md` before
using it. `fleetchaser-backend-1` ran that checkout mounted at `/app` when verified.
Confirm current mounts before executing queries. Use a read-only Django transaction.
Mount verification identifies the code checkout, not the freshness or authority of
its database. The local development database can be an older production copy: zero
same-day audit rows there is incomplete coverage, not proof of no workboard activity.
Use an available authorized live read path when necessary to establish a task outcome;
otherwise state the gap without refreshing or syncing the database.

`task.models.audit_log.TaskAuditLog` provides `created`, `created_by`, `task`, `action`,
and `meta_data`. Inspect `task/models/choices.py` for action codes; actual examples
are `t:m` (move), `t:c` (create), and `a:r` (assignee removal), not English enum names.
Resolve `meta_data.status` and previous status through `WorkflowStatus`; distinguish
real transitions from reordering. The actor is an `authentication.Employee`.
Query all relevant user audit events within the day, including moves later reversed,
rather than only tasks currently completed. Resolve names/IDs and include creation,
assignment, and completion work without counting one action multiple times.

Installs → Bill means field work is complete and ready for billing. It does not mean
the invoice was created/paid or that Dmitry personally performed the field work.
Exclude Marketing keyword tasks and test workflows from service-work counts.

## Linear completion and cancellation history

Local candidates: `ops_linearissuelink`, `linear_issue_state_events`, and
`ops_linearhumanaction`. The latter has `occurred_at`, `actor`, `kind`, `detail`,
`link_id`, and `linear_issue_id`. Link rows use `issue_id` for the remote UUID and
`issue_identifier` for keys such as OPS-1405; they do not have `linear_issue_id`.

Verify actual transitions and actors with live Linear. The existing read client is
`ops.clients.linear._post(query, variables)` inside `ops-backend`. Use query-only
GraphQL, following the [official API guide](https://linear.app/developers/graphql)
and [filtering guide](https://linear.app/developers/filtering). Check current schema
when needed; errors and pagination must not be treated as empty results.

Issue fields: `identifier`, `title`, `url`, `completedAt`, state, and
`history { nodes { createdAt actor { name email } fromState { name type }
toState { name type } } pageInfo { hasNextPage endCursor } }`.

Collect issues completed in the window plus locally recorded day transitions and
relevant recently updated issues; inspect history to catch same-day Done followed
by reopening. Paginate candidate issues and their histories. Count only transitions
made by the requested user within the day. Separate Done, Canceled, For Review, and
developer Ready for Deploy states. A local `completed_at` can be populated for a
canceled item; it is not authoritative evidence of Done. Deduplicate reopened/reclosed
items in completion totals and describe the end-of-day outcome accurately.

## Evidence notes

For each reported outcome record source ID/link, timestamp, actor, company, what the
source actually proves, and any remaining uncertainty. For company problems, record
the concrete customer/business impact and the evidence for resolution or recurrence.
Keep raw histories and customer data in the dated local run directory, not the repo.
