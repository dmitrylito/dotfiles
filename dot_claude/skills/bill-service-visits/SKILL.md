---
name: bill-service-visits
description: Bill Fleet Chaser service visits from the Installs/Bill workboard column - discover live tasks, gather install evidence, dry-run the service-visit-lines API, ask Dmitry which tasks to bill via a selection prompt, apply, verify, and move billed tasks to Completed. Use when asked to "do the service billing", "bill the tasks", "run service visit billing", or "bill the Bill column".
---

# Bill service visits

One invocation, one selection prompt, then apply. Driver: `~/.claude/skills/bill-service-visits/svb.py`
(stdlib, run from any cwd, `--help` for flags). Artifacts land in
`~/.local/state/service-visit-billing/<date>/`; nothing is written to the backend until `apply`.

## Requirements (read before running)

- **The target backend must serve the billing app**: `POST /api/billing/service-visit-lines/`
  and the `billing` models (`Invoice`, `InvoiceLineItem`, product `service-fee`). As of
  2026-09-17 that exists only on branch `dmitrylito/billing-app` (+ `service-visit-candidates`
  worktree), not on master/prod. Until billing is merged and deployed, the only valid target
  is the local stack (`backend.dlco.us` == `localhost:8000`, same DB).
- **Prod later**: when billing ships, point `BACKEND_API_URL` / `BACKEND_API_TOKEN` (env or
  `--env-file`) at prod with an admin API key, and run `evidence`/readback against a checkout +
  DB that mirror prod (the nightly local copy is fine for evidence; readback must query the
  DB the API wrote to). The API is the contract; the driver has no prod-only code paths.
- Containers: `ops-backend` (ops-center, live FC task mirror + `update_fc_task`) and the backend
  compose stack at `~/Projects/backend/docker/docker-compose.yml`. Pass `--checkout <path>`
  when the main checkout lacks the billing models (it sets `PROJECT_PATH` for compose).
- Env file default: `~/Projects/billingapp/docker/envs/billingapp.env`. Never print the token.

## Decisions already made (do not re-ask)

- Service fee is **$150.00** per task (`--unit-price` only if Dmitry says otherwise).
- Service date = task `completed_at` in `America/New_York`. Show install-date mismatches as
  warnings; don't silently substitute.
- Every task that receives a line, appended or new draft, moves **Bill → Completed**
  (Installs status id 4) right after apply. Not "Billed" (5); Bill column means "unbilled".
- Skipped tasks stay in Bill. Never move a task that got no line.
- Customers with `telemetry_unit_price = 0` (e.g. Carolina Curb & Gutter) have free tracker
  hardware by design; don't flag their trackers as missed billing.
- No ChargeOver export here. Export is the separate admin flow in backend `docs/billing.md`.

## Procedure

1. `svb.py discover` - live Installs/Bill tasks from ops-backend → `tasks.json`. If empty, stop.
2. `svb.py [--checkout …] evidence` → `manifest.json` + review printout per task: customer
   match, target (`append <invoice>` / `NEW draft`), install/camera/vehicle records ±4/3 days,
   warnings (date mismatch, shared hardware records between two tasks, existing line, no
   evidence, unbilled customer), and a drafted customer-facing `work_performed`.
   - Unresolved customer: pick from the printed suggestions, add
     `"<company name>": "<customer uuid>"` to `~/.local/state/service-visit-billing/customer-map.json`,
     rerun `evidence`. Never guess a customer.
   - Edit `work_performed` in `manifest.json` where the draft is wrong or the task text is the
     only source (say so in the prompt). Descriptions must describe backend-evidenced work, no
     installer notes, no task ids. The API prefixes `Service fee for site visit on <date>: `.
3. `svb.py preview` - dry run of every resolvable item. All rows must be `ready` or
   `already_exists`; fix `error` rows before the prompt.
4. **Selection prompt** with `AskUserQuestion`, multi-select. Up to 4 questions × 4 options per
   call, so group tasks 4 per question ("Bill which of these? (1/4)"); more than 16 tasks →
   a second call. Option label: `#4037 Axtraction → append 10000006` or `→ NEW draft`.
   Description: evidence one-liner + warnings (⚠ date mismatch, ⚠ same visit as #4007, ⚠ no
   hardware records). Unselected = skip. Tasks with `already_exists` are informational, not
   options. Add a fourth question only when something needs a decision beyond select/skip
   (duplicate pair: which one; price override).
5. `svb.py apply --keys fc-task:…,…` - resubmits the exact previewed items with `apply: true`
   (refuses if an item changed since preview), then DB readback. Verify every key came back
   with product `service-fee`, qty 1, $150, expected invoice. Stop on any `error` row.
6. `svb.py move-tasks --keys <same keys>` - Bill → Completed; confirm each prints `Completed`.
7. Report: appended (task → invoice, new total), new drafts (task → invoice), skipped (still in
   Bill), warnings you overrode, artifact dir. Say plainly that nothing was exported.

## Gotchas

- `discover` reads the ops-center mirror, which syncs continuously; the local backend DB is a
  nightly copy, so a task finished today has no install records yet (evidence warns
  "no hardware records"). Bill from task text only if Dmitry accepts that in the prompt.
- Two tasks sharing the same install records is one visit billed twice; the warning names the
  pair. Offer one, default the earlier task id.
- `already_exists` with identical values is safe; a reused key with different values fails
  closed. Never bypass by changing the key.
- Cloudflare fronts `backend.dlco.us`; the driver sends a User-Agent so urllib isn't 403'd.
- Supersedes the backend/ops-center project skill `service-visit-billing` for day-to-day runs;
  that one remains the policy reference (evidence, authorization, export boundaries).
