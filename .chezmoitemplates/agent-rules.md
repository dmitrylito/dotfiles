# Shared global agent rules

These rules apply across projects. Follow the user's current instructions and the
repository's more specific architecture, runtime, validation, and authorization
rules. Complete necessary, scoped steps of an authorized task without asking again.
Ask when an action materially expands scope or crosses an explicit authorization
boundary. Tool permissions and old memories do not independently authorize work.

## Communication and efficient execution

- Update me for meaningful results, sustained stalls/failures, or decisions needing my input; ask only when missing information or authorization blocks safe progress.
- Keep routine monitoring in a durable process, not repeated model turns. Validate fixtures before expensive runs, reuse completed checks, and use a compact handoff before a long session's context becomes costly.

## Instruction files

- Use `AGENTS.md` as the canonical project guide when creating or maintaining
  instructions. Put scoped guidance in subdirectory `AGENTS.md` files when needed.
- Tool-specific instruction entry points may link to `AGENTS.md`. Report conflicting
  legacy guides; consolidate them within an instruction-maintenance task, not as a
  side effect of unrelated work. Preserve unique guidance during consolidation.
- Keep executable hooks, permissions, and MCP configuration in the owning tool's
  config files. Project guides may explain relevant boundaries and link to skills.

## Current documentation

- Verify external behavior against version-appropriate official documentation when
  correctness, compatibility, or a decision depends on it. Check installed or pinned
  versions; documentation lookup is not a reason to upgrade dependencies.
- Read and cite the relevant official page. Use provider documentation tools or
  Context7 when they supply appropriate official content; otherwise fetch the
  official page. Distinguish verified facts from inference or uncertainty.
- Reuse documentation already verified for the same version and question, and
  established repository commands when applicable. Avoid repeated lookups that
  cannot affect the decision. General language concepts, repository business logic,
  and routine use of verified commands do not require another lookup.

## Long-running jobs and efficient monitoring

- When asked to run and monitor a job, retain responsibility through completion,
  failure, cancellation, or its configured deadline. A long runtime alone is not a
  reason to abandon monitoring or ask the user to check back manually.
- Use a process or existing job runner for routine polling, health checks, log
  collection, and bounded retries. These checks should not invoke a model. Wake the
  agent for completion, failure, a sustained stall, or a decision requiring judgment.
  Deduplicate repeated alerts and coalesce progress; do not replay the conversation
  merely to discover that nothing changed.
- Prefer native completion events or a durable watcher with a verified notification
  path. Before promising automatic follow-up, verify that the current environment
  can deliver an event to the agent after yielding. A log file, detached process,
  desktop notification, or sleep loop alone does not establish that capability.
- If automatic agent notification is unavailable, keep process-level monitoring
  running and explain the delivery limitation. Use model-driven polling only as an
  explicit fallback with a task-appropriate interval, deadline, and model-call budget.
  Do not silently substitute frequent conversational checks for a watcher.
- At launch, record the check interval, stall threshold, deadline, retry limits,
  notification destination, and log/output caps. Choose sensible values for the job
  within the user's scope; do not require confirmation for routine monitoring setup.
  Bound retries of both the job and notification delivery. A monitoring deadline
  triggers a report; it does not authorize killing the underlying job.
- Keep unattended, overnight, and bulk jobs durable outside disposable worktrees or
  scratch storage. Record the command, working directory, relevant ref, start time,
  and job identifier without secrets. Capture logs and an atomic terminal marker
  with outcome, exit code, and finish time. A missing marker means unknown, never
  success. Detect missing heartbeats or exited processes independently of the marker.
- Report job, log, status, and stop paths at launch. On a meaningful event, inspect
  only the changed state and relevant log excerpt, verify the outcome, and continue
  already-authorized follow-up. Monitoring does not authorize unrelated remediation.
- Bounded foreground builds and checks may use blocking tool waits or completion
  events with an explicit timeout. Avoid repeated short waits that return control
  to the model just to wait again; do useful independent work while tools run.
- There is no fixed cap on process-level checks or meaningful completion events.
  Honor explicit user spending limits. Use model-call budgets for polling fallbacks
  and repeated diagnosis; do not disable a healthy watcher based on a shared weekly
  usage meter that cannot attribute usage to this job.
- Keep wakeup context small: job manifest, latest state, and bounded evidence. Use
  a compact handoff where supported, preserving authorization and project rules.
  Do not silently lower model quality as a substitute for removing needless calls.

## Worktrees and runtime verification

- Create feature and PR worktrees as siblings: <parent>/<repo>-<short-task-slug>.
  Use this globally unless the user or project explicitly requires another path.
  Do not default to worktrees inside .codex/, .claude/, or the main checkout.
- Inspect registered worktrees and reuse the appropriate existing one. Do not move
  or delete worktrees merely to enforce this convention. Preserve concurrent work.
- Run feature edits, checks, commits, and PR commands from its worktree. Use the
  main checkout for operations that explicitly require it. Chezmoi source edits
  must use the real source directory because apply does not read a feature copy.
- Before checking or generating files through a container, remote runtime, or
  shared service, verify which checkout/ref it actually runs. Changing the shell's
  working directory does not change a container bind mount. Use the project's
  supported isolated runtime for the feature; never claim main-checkout tests
  validate a different worktree or silently repoint a shared environment.
- State the worktree path and branch when creating or taking over a PR. A command's
  working directory does not switch the session root or its statusline.

## Working conventions

- Make the smallest cohesive change and match surrounding code. Keep business
  logic in the owning service/domain layer; follow the project's choice of pure
  functions or classes rather than imposing a global class-only architecture.
- Explain a material tradeoff once. Once the user chooses, execute that direction;
  do not quietly change the objective or add unrequested optimization targets.
- Make operational budgets, retry limits, and output caps explicit configuration.
  Use stored data or fixtures for checks when usable; respect the repository's
  boundaries before making live external calls or changing shared data.
- Report the outcome plainly, with evidence, relevant checks and their results,
  skipped checks, and any necessary follow-up. Never claim a deploy or remote
  change without performing it and reading back the resulting state.
- Verify memory-derived operational commands and paths against current code/docs
  before using them. Treat old deployment, branch, and cleanup notes as historical.

## Managed configuration

- Check chezmoi status and source Git status before changing managed dotfiles.
  Edit the source under ~/.local/share/chezmoi, not just the deployed target.
  Preserve profile branches and unrelated source or runtime changes.
- Preview and apply only the intended targets; verify their rendered contents
  and check for drift afterward. Respect the source repository's documented
  commit/push workflow; do not broaden an apply to unrelated changes.
- Back up files outside Git or chezmoi before modifying them. Verify the actual
  host role and runtime before making host-specific changes.
