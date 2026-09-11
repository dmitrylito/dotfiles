# Code style

Default to no comments and no docstrings — well-named functions, variables, and small
focused units are the documentation. The repository's own agent/style guide wins if it says so.

- Comment ONLY to prevent a real mistake: a non-obvious constraint, a footgun, a subtle
  invariant not visible in the code. Explaining *why* can justify a comment; explaining
  *what* the code plainly does never does — that's noise.
- This bar applies to EVERY edit, not just new files: never add a comment while modifying
  existing code unless it meets the bar, and when your own diff introduces narration
  comments ("# now filter", "# call the helper"), delete them before finishing.
- Before completing any code task, re-scan the diff for comments; each one must justify
  itself as mistake-prevention or be removed.
- Keep any necessary comment to one short line; put longer context in the commit/PR.
- No ordered/step markers (`# 1. …`, `# now …`) — the structure already shows the flow.
- Docstrings only for a real public contract or non-obvious boundary, never boilerplate
  that echoes the signature.
- Functional "comments" are code — never strip `# type: ignore`, `# noqa`, `# pragma`,
  `# fmt: off/on`, shebangs, or encoding lines.

## Exception: agent-authored tooling documents itself

The opposite rule applies to code written for MY OWN future use — skills, helper scripts,
hooks, workflow scripts, anything a future session runs without this session's context:
give it a short header stating purpose, usage/invocation, and any preconditions
(env vars, tokens, expected cwd). A future session reads it cold; product code has
humans and reviews, agent tooling has only its own text.
