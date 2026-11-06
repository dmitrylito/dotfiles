---
name: state-mileage-import
description: Generate a State Mileage (IFTA) report locally for the vehicles and date range Dmitry gives — imports production readings, regenerates GPS odometer miles and HourlyStateMileageRollup for just that window, ready to pull from the local frontend. Use when asked to generate/regenerate a state mileage or IFTA report, import/sync vehicle readings, or reprocess odometer miles for vehicles.
---

# Local State Mileage Report (one-off)

One run per request: the vehicles and dates Dmitry gives, regenerated in the local dev
DB, then he pulls the report from the local frontend. No backups, no scheduling — the
nightly DB refresh wiping it afterwards is fine.

## 1. Resolve vehicle IDs

```sql
SELECT v.id, v.identifier, c.name, c.timezone
FROM vehicle_vehicle v JOIN accounting_customer c ON c.id = v.customer_id
WHERE c.name ILIKE '%<customer>%' AND v.identifier ILIKE '<name>%' AND v.deleted IS NULL;
```

Identifiers often carry VIN suffixes (`JH# 6 DT VIN 1M2P…`) and deleted same-named
duplicates — match by prefix, filter `deleted IS NULL`. Ask only if a name is ambiguous.

## 2. Run the pipeline

```bash
bash ~/.claude/skills/state-mileage-import/run_pipeline.sh <ids_csv> <first_day> <last_day>
# e.g. Q3 2026:  run_pipeline.sh 3502,6508 2026-07-01 2026-09-30
```

Dates are inclusive `YYYY-MM-DD` in each vehicle's customer timezone (looked up
automatically). Run it in the background; a quarter of one truck is ~300k readings,
~10 min. It stops with a non-zero exit if the replay saw fewer readings than were
imported or if the rollup total doesn't equal the regenerated miles.

Only rows inside the window are replaced; everything outside it is untouched. The
script prints, per vehicle, miles by month and state — report those numbers.

**Never run two pipelines at once**: the emulator is in-memory and gets OOM-killed
around ~2M rows, and every vehicle restarts it (wiping ALL emulator data). Check
`ps aux | grep dev_sync_readings` first.

A vehicle with readings but ~0 miles may genuinely be parked; confirm on a sample of
readings before calling it a bug.

## 3. Pull the report

`https://console.dlco.us/reports/ifta` (Reports → State Mileage): log in, switch into
the vehicles' customer, set the same date range. If it's 502, start the dev server
(nginx proxies 4200; `PORT=8083` is exported in the shell, so unset it):
`cd ~/Projects/frontend && unset PORT && bunx ng serve frontend -c local --host 0.0.0.0 --port 4200`
(needs `allowedHosts: ["console.dlco.us"]` under the serve target options in
`angular.json`). If the main frontend checkout doesn't compile, serve from a clean
worktree and copy in the gitignored `src/environments/environment.local.ts`.

## Why it works this way (don't "simplify" to these)

- Miles come from GPS, not the vehicle's live source: a frozen or under-counting ECU
  odometer is the usual reason a report is wrong (JH# 6, 2026: ECU ~30% low, then
  frozen from 2026-08-20).
- Rollups are one mile per odometer row per (hour, state), not
  `HourlyStateMileageRollup.objects.add_odometer`: that takes `max(mile) - min(mile)`
  per state per hour and double-counts in-hour border crossings (+105 mi on JH# 6 Q3).
- `reprocess_vehicle_stats` needs a migration-reason TrackerInstall
  (`installs.get(reason='mig')` raises for most vehicles) and mutates installs.
- `pipeline.tasks.ReprocessVehicleInRange` does NOT regenerate odometer miles — for a
  list of readings, `ReadingIntake.process` never runs `OdometerProcessor`.
- `Odometer` is unique on `(vehicle, mile)`: new miles continue from the last
  pre-window mile, or number above the vehicle's max if that would collide with rows
  after the window.
