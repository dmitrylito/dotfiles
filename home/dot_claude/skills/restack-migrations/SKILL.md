---
name: restack-migrations
description: Fake-roll-back, delete and regenerate a branch's Django migrations so they sit on top of master, squashed to one schema migration per app. Use after rebasing a feature branch onto master, when migrations collide (duplicate numbers, "Conflicting migrations detected; multiple leaf nodes"), or when asked to restack / renumber / squash a branch's migrations.
---

# Restack branch migrations onto master

A rebase moves commits, not migration numbers. A branch that added `tracker/0015_x`
while master also grew a `tracker/0015_y` ends up with two leaf nodes, and every
`manage.py migrate` then fails outright. This restacks the branch's migrations to
sit after master's, one regenerated schema migration per app.

Written for the Fleet Chaser backend layout: a compose-based Django project with a
`backend` service and `manage.py` at the repo root.

## Run it

From the repo root of the project, after the rebase:

```bash
python3 ~/.claude/skills/restack-migrations/restack_migrations.py plan     # read-only
python3 ~/.claude/skills/restack-migrations/restack_migrations.py run      # prompts once
python3 ~/.claude/skills/restack-migrations/restack_migrations.py verify   # re-check later
```

Flags: `--base <ref>` (default `master` — use `prod` etc. for branches off another
base), `--mode auto|fake|real`, `--interactive`, `--yes`, `--force`.

Always show `plan` output before running `run`, and stop if `plan` reports
migrations the branch **modifies** (rather than adds) — the script leaves those
alone and they usually need a human decision.

## Environment

`manage.py` runs in the container (the host cannot reach `DB_HOST=db`), resolved in
this order:

1. `RESTACK_MANAGE` — full override, e.g. to target a scratch DB:
   `export RESTACK_MANAGE='docker compose run --rm --no-deps -T -e DB_NAME=scratch backend ./manage.py'`
2. `docker compose exec -T backend ./manage.py` when the dev stack is up
3. `docker compose run --rm --no-deps -T backend ./manage.py` otherwise

`docker compose` relies on **`COMPOSE_FILE`** when it is exported — which the
backend repo's `.envrc` does via direnv — and falls back to
`-f docker/docker-compose.yml` for non-interactive shells where the direnv hook
never fires (agents, cron, `bash -c`).

That fallback matters because `COMPOSE_FILE` is absolute: inside a **worktree**, a
`COMPOSE_FILE` pointing at the main checkout makes the container mount the *main*
checkout at `/app`, so `makemigrations` would read the wrong code. The script
refuses to run on that mismatch and prints the fix (`export PROJECT_PATH=$PWD`).
A worktree also needs `docker/.env` copied in (it is gitignored) or compose fails.

## What `run` does

1. Reads `django_migrations` for the affected apps to see which branch migrations
   are recorded in the dev DB.
2. Backs every branch migration up to `.claude/restack-backup-<timestamp>/`.
3. **Fake-unapplies** the recorded ones by deleting only their `django_migrations`
   rows — the schema is left exactly as it is. Row deletion is used instead of
   `migrate --fake` on purpose: with a conflicted graph, `migrate` refuses to run
   at all, so there is no way to fake-reverse through it.
4. Deletes the branch's migration files.
5. `makemigrations <apps>` → one fresh schema migration per app, numbered after
   master's leaf.
6. Re-materializes the branch's **data** migrations (anything containing
   `RunPython` / `RunSQL` / `SeparateDatabaseAndState`) verbatim, renumbered after
   the regenerated schema migration, in their original order, with every
   dependency on a now-deleted migration repointed at its replacement.
7. Applies: `--mode fake` (branch schema already in the dev DB) or a real
   `migrate` (it wasn't — e.g. the nightly prod refresh wiped it). `auto` picks
   based on step 1.
8. Verifies: `makemigrations --check --dry-run` (no model drift) plus
   `migrate --plan` (single leaf per app).

Then commit: `git add -A <app>/migrations …` — the paths are printed at the end.

## Things to know

- **Data migrations are never regenerated.** `makemigrations` cannot recreate a
  `RunPython`, so hand-written seeds/backfills are copied, not rebuilt. That is
  why the result is "one *schema* migration per app + the original data
  migrations", not literally one file.
- **Squashing puts all schema first.** If a branch relied on
  backfill-then-tighten ordering (data migration between two schema migrations,
  e.g. populate a column and only then make it non-null), the squash reorders it
  and the verification below is the only thing that catches it:
  ```bash
  docker compose run --rm backend ./manage.py test <app> --noinput
  ```
  No `--keepdb` — it builds the test DB from zero, which is the only real proof
  the new order works on a fresh database. `migrate --plan` on an
  already-migrated dev DB proves nothing about ordering.
- **A cross-app FK cycle can force a split.** If app A's models FK into app B and
  B's FK back into A, `makemigrations` emits two files for one of them. The script
  reports this and leaves it — that split is required, not a failure.
- **Some model changes cannot be regenerated unattended.** `makemigrations --no-input`
  exits 3 rather than inventing an answer for a new non-nullable field or an
  `auto_now_add` without a default, and it declines rename detection (turning a
  rename into drop-column + add-column). If `run` hits this it **restores the
  branch to exactly how it was** — files back from the backup, `django_migrations`
  rows re-recorded — and tells you to re-run with `--interactive` so you can answer
  the prompts. Watch for silent renames in the regenerated file either way.
- **Partial dev-DB state makes it stop.** If only some of the branch's migrations
  are recorded, neither mode is safe to guess (`fake` would mark the unapplied ones
  applied; `real` would re-run the applied ones), so it refuses and asks for an
  explicit `--mode`.
- **Only the `default` database is handled.** `TelemetryRouter` keeps the
  telemetry-DB models off `default`, and `migrate --database=telemetry` records its
  own `django_migrations` rows. If a branch adds migrations to a telemetry-routed
  app, the unrecord and apply steps must be repeated by hand with
  `--database=telemetry`, or that DB will keep rows under the old names and try to
  recreate existing tables.
- **Only ever restack unmerged migrations.** Renaming a migration that some other
  database already recorded (prod, staging, a colleague's dev DB) makes it look
  unapplied there and it will be re-run.
- **Recovery** is always available: everything deleted is committed on the branch,
  so the printed `git checkout HEAD -- <paths>` restores it, and the backup dir
  holds byte-identical copies.
