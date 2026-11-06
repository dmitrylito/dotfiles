---
name: bill-service-visits
description: Bill Fleet Chaser service visits from the Installs/Bill workboard column - discover live tasks, classify each vehicle with the service-fee rules, dry-run the service-visit-lines API, ask Dmitry which tasks to bill via a selection prompt, apply, verify, move billed tasks to Completed, then preflight and export the drafts to ChargeOver prod with the tracker/camera handoff CSVs. Use when asked to "do the service billing", "bill the tasks", "run service visit billing", "bill the Bill column", or "export the invoices to ChargeOver".
---

# Bill service visits

One invocation, one selection prompt, then apply; export is a second, explicit OK. Agent-agnostic:
lives in `~/.agents/skills/bill-service-visits/` (symlinked from `~/.claude/skills` and
`~/.codex/skills`). Driver: `~/.agents/skills/bill-service-visits/svb.py` (stdlib, run from any
cwd, `--help` for flags). Artifacts land in `~/.local/state/service-visit-billing/<date>/`;
nothing is written to the backend until `apply`, and nothing reaches ChargeOver until
`export --yes`.

## Requirements (read before running)

- **The target backend must serve the billing app** on the local stack (`backend.dlco.us` ==
  `localhost:8000`, same DB): `POST /api/billing/service-visit-lines/` with `quantity`,
  `GET /api/billing/billable-groups/`, and payment scheduling in the export. As of 2026-10-27
  that is `dmitrylito/billing-app` at or after `44d431c0b` (local checkout; not on master/prod).
- Containers: `ops-backend` (ops-center, live FC task mirror + `update_fc_task`) and the backend
  compose stack at `~/Projects/backend/docker/docker-compose.yml`, including
  `fleetchaser-fleet_worker-1`, which runs the export task. After changing billing code,
  `docker restart fleetchaser-fleet_worker-1`. `--checkout <path>` sets `PROJECT_PATH` for the
  helper containers.
- Env file default: `~/Projects/billingapp/docker/envs/billingapp.env`. Never print the token.
  ChargeOver prod credentials come from the backend's `docker/.env`.
- **The 05:00 nightly `import-db` wipes local drafts and skips.** Apply and export the same day.

## Decisions already made (do not re-ask)

- Service fee is **$75.00 per vehicle worked on**: one line per task, `quantity` = billable
  vehicles. `evidence` computes it per vehicle:
  - counts: new tracker/camera install (a vehicle getting both counts once), hardware moved
    from a sold truck into a replacement truck (Toro 715), tracker replaced when the old unit
    is a year old or more, tracking restored on a tracker a year old or more (vehicle named in
    the task).
  - does not count: camera swaps/repairs, SIM swaps, removals, warranty work (the replaced or
    restored unit is under a year old, whatever the vehicle's age), customer self-installs
    (install row created by a non-staff login, e.g. Charlotte Steel TK11, Wood Harvest).
- Exemptions live in `~/.local/state/service-visit-billing/exemptions.json`
  (`{"<customer name or uuid>": "<reason>"}`); Heaven and Earth Landscaping is exempt.
  One-off calls (United's PT-53 install, ELS's 10-21 move, Helms, EGC on 2026-10-27) are made
  in the selection prompt, not added to the file.
- Hold a visit whose hardware is still inside the 5-day billing wait; evidence warns.
- Service date = task `completed_at` in `America/New_York`. Show install-date mismatches as
  warnings; don't silently substitute.
- Every task that receives a line moves **Bill → Completed** (Installs status id 4) right after
  apply. Not "Billed" (5). Skipped tasks stay in Bill; never move a task that got no line.
- Customers with `telemetry_unit_price = 0` (e.g. Carolina Curb & Gutter) have free tracker
  hardware by design.
- Export schedule = ChargeOver's "Invoice now, charge in 30 days": an `inv` step tomorrow
  (Eastern; ChargeOver rejects same-day dates) that makes ChargeOver email the invoice, then
  100% on the newest ACH (else newest card) at invoice date + 30. No ACH/card → email step only.
  Never call ChargeOver's `_action/email` (Dmitry, 2026-10-27).

## Procedure

1. `svb.py discover` - live Installs/Bill tasks from ops-backend → `tasks.json`. If empty, stop.
2. `svb.py evidence` → `manifest.json` + per task: customer, target draft, one line per vehicle
   (`✔`/`✘` with the reason: new, moved from X, warranty with old-unit date, camera swap,
   self-install by <login>, `[app: new_vehicle|replacement]` from billable-groups when the
   hardware is still pending), warnings, and `=> N vehicle(s) x $75 = $… : <work_performed>`
   or `=> no line: <reason>`.
   - Unnamed `tracker_online` vehicles are listed but never counted; add one only if Dmitry
     confirms (edit `quantity` and `work_performed` in `manifest.json`).
   - Unresolved customer: pick from the printed suggestions, add
     `"<company name>": "<customer uuid>"` to `customer-map.json`, rerun `evidence`. Never guess.
   - Overrides go in `manifest.json` (`quantity`, `work_performed`). Descriptions describe
     backend-evidenced work only; the API prefixes `Service fee for site visit on <date>: `.
3. `svb.py preview` - dry run of every item with quantity > 0. All rows `ready` or
   `already_exists`; fix `error` rows first.
4. **Selection prompt**, multi-select, one task per option (Dmitry prefers individual options
   over groups): `AskUserQuestion`, 4 questions × 4 options per call, more calls as needed.
   Label `#4037 Axtraction → append 10000006` / `→ NEW draft`; description = vehicles, $ and
   the reasons/warnings. List the no-line tasks with their reasons in the question text so
   skips are visible. Unselected = skip.
5. `svb.py apply --keys fc-task:…` then check the readback (service-fee, qty, $75, invoice).
6. `svb.py move-tasks --keys <same keys>`; confirm each prints `Completed`.
7. `svb.py preflight` - read-only ChargeOver checks on every local draft: inactive customer
   (export would fail; reactivate with `POST /customer/<id>/_action/setActive` only if Dmitry
   says so), no ACH/card (email only), newest card expired (30-day charge will fail). Show the
   list and totals and get an explicit OK.
8. `svb.py export --all-drafts --yes` (or `--invoices k,k`): reruns preflight, skips inactive
   customers, queues the same `ExportSelectedInvoicesTask` as the admin "Send reviewed drafts to
   ChargeOver (prod)" action, waits, reads back each invoice (local status, ChargeOver id and
   total, schedule), writes the tracker/NGVR handoff CSVs and copies them to
   `$SSH_CLIENT_HOST:~/Downloads`. Without `--yes` it is a dry run.
9. Report: lines added (task → invoice), skipped tasks and why, exported invoices with schedule,
   anything flagged (no pay method, expired card, failed export), handoff file paths.

## Gotchas

- Vehicle records are sometimes reused (an old vehicle renamed for a new truck, e.g. Stronghold
  "17 Volvo Jacob Trans"). Evidence then reads earlier installs as a replacement and warns
  "reused vehicle record?"; Dmitry treats it as a move, so override to billable.
- Two tasks sharing install records is one visit billed twice; the warning names the pair and
  each task counts every shared vehicle. Split them by task text or offer one.
- FC app forms (Install Form 46, Device Repair 30, Service Visit 43) were barely used as of
  2026-10-27; extra evidence at most.
- `discover` reads the live ops-center mirror; the local backend DB is a nightly copy, so a task
  finished today has no install records yet ("no hardware records").
- `already_exists` with identical values is safe; a reused key with different values fails
  closed. Never bypass by changing the key. To change a line already applied, edit it in Django
  admin (or the ORM) and recalculate the invoice total.
- A failed cross-database export is not retryable by the task. Only if ChargeOver shows no
  invoice for that customer, set the local invoice back to `draft` and export again.
- ChargeOver staging (`fleetchaser-staging2`) returned "Trial Expired" (HTTP 402) on
  2026-10-27; there is no safe sandbox.
- Cloudflare fronts `backend.dlco.us`; the driver sends a User-Agent so urllib isn't 403'd.
