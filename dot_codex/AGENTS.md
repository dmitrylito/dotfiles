Use current official documentation for library, framework, SDK, API, CLI, and cloud-service questions. Prefer primary sources and cite the documentation used.

## Usage safety

- Never supervise a long-running process with frequent model-driven `wait`, `write_stdin`, status, or log-polling loops. A local process can run without Codex repeatedly waking up.
- For work expected to run longer than five minutes, make the batch process own its retries and progress reporting, write a durable log and completion marker, launch it once, and return control to the user. Inspect it again only when the user asks or when an event-driven completion mechanism wakes the session.
- Never poll merely to provide a conversational update. Report only new evidence.
- If the user explicitly requests active monitoring and no event-driven mechanism exists, poll no more than once every 15 minutes and stop autonomous monitoring after 10 model wakeups or a two-percentage-point increase in the visible weekly limit, whichever happens first. Leave the underlying local job running and report that the usage guard stopped Codex monitoring.
- Before unattended, overnight, or bulk work, record the visible weekly-limit baseline and use a fresh or compacted thread when the current context is large. Do not run bulk supervision from a long-lived investigation thread.
- Continuous monitoring beyond these limits requires the user's explicit approval of a larger usage budget. A request to run the underlying job is not approval for unlimited Codex polling.
- Do not silently lower model quality to save usage. Prevent repeated context replay first; offer a cheaper model separately when it is appropriate.

## Worktree convention (2026-09-09)

- Create Codex feature and PR worktrees as siblings of the main repository: `<parent>/<repo>-<short-task-slug>`. For example, `~/Projects/ops-center-answered-questions` beside `~/Projects/ops-center`.
- Use this layout globally unless the user or a project-specific instruction explicitly requires another location. Do not default to worktrees inside `.codex/`, `.claude/`, or the main checkout.
- Inspect registered worktrees first and reuse the appropriate existing worktree. Do not move or delete existing worktrees merely to enforce this convention.
- Run the feature's edits, tests, commits, and PR commands from its worktree. Use the main checkout for operations that explicitly require it, such as ops-center deployment.
- State the worktree path and branch when creating or taking over a PR. A per-command working directory does not change the session root or its statusline; do not claim that the session switched automatically.
