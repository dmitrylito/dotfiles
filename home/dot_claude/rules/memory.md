# Proactively save durable knowledge to memory

When something surfaces that will matter in future sessions, save it to auto-memory
(one file per fact) WITHOUT waiting to be asked — and always when the user says "remember …".
On fcoffice every project shares one dir, `~/.claude/memory/`; elsewhere it is per project
(`~/.claude/projects/<slug>/memory/`).

- A stated preference or correction about how I should work → type `feedback`
- A non-obvious project/infra fact not derivable from the code → type `project`
- Who the user is or how they operate → type `user`
- A pointer to an external resource (URL, dashboard, ticket) → type `reference`

Rules: one fact per file; update the matching file instead of duplicating; keep
`MEMORY.md`'s one-line index in sync, under the matching `##` area heading;
prefix repo-specific descriptions with the repo name; cross-link related memories with `[[name]]`.
Only the first 200 lines / 25KB of `MEMORY.md` load, so keep index lines short and merge
or delete stale entries rather than appending.
Don't save secrets, transient state, or anything the repo/CLAUDE.md/rules already record.
