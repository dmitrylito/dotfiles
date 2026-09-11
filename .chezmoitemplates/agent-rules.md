# Shared global agent rules

These rules apply across projects. Follow the user's current instructions and the
repository's more specific architecture, runtime, validation, and authorization
rules. A tool permission or an old memory is not authorization for a new action.

## Current documentation

- Use current official documentation for library, framework, SDK, API, CLI, and
  cloud-service questions, including familiar tools and routine usage. Do not
  substitute remembered syntax or behavior for verification.
- Check the project's installed or pinned version and use matching official docs;
  current documentation does not mean silently upgrading to the latest version.
- Retrieve and read the relevant official page. Cite the documentation actually
  used, and distinguish verified facts from inference or unresolved uncertainty.
- Context7 or a provider's documentation tool is useful when it supplies relevant
  official, version-appropriate content. Otherwise use official-site search and
  fetch the page directly. Tool availability must not become a reason to guess.
- Reuse documentation already verified in the current task when the version and
  question have not changed. General language concepts and repository business
  logic do not require a documentation lookup unless external behavior matters.

## Long-running jobs and usage safety

- Never supervise a long-running process with frequent model-driven waits,
  status checks, log reads, or polling loops. Never poll just to provide an update.
- For work expected to run longer than five minutes, let the process own its
  retries and progress reporting. Launch it once using a durable background
  mechanism, then return control to the user. Inspect again only when asked or
  when an event-driven completion notification wakes the session.
- Before launch, establish a durable job directory outside disposable worktrees
  and ephemeral scratch storage. Record the command, working directory, relevant
  commit/ref, start time, and configured retry limits without exposing secrets.
- Capture stdout/stderr in a durable log. Have the process write a terminal marker
  containing success or failure, exit code, and finish time on normal termination.
  Write the marker atomically. A missing marker means incomplete or unknown,
  never success. A killed process or host failure may prevent marker creation.
- Give the user the job identifier, log and marker paths, and how to inspect or
  stop it. Keep credentials and sensitive payloads out of logs and manifests.
- If active monitoring is explicitly requested and no completion event exists,
  poll at most once every 15 minutes. Stop autonomous monitoring after 10 model
  wakeups or a two-percentage-point increase in the visible weekly usage limit,
  whichever happens first. Leave the underlying job running and report the stop.
- Before unattended, overnight, or bulk work, record the visible weekly usage
  baseline and use a fresh or compacted thread when the context is large. If the
  metric is unavailable, record that fact; do not invent it. The time and wakeup
  limits still apply. Do not supervise bulk work from a long investigation thread.
- Monitoring beyond these limits requires an explicit larger usage budget.
  Authorization to run a job is not authorization for unlimited monitoring.
- Do not silently lower model quality to save usage, including for delegated work.
  Prevent repeated context replay first; offer a cheaper model separately.

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
