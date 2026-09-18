# Codex setup

Global Codex instructions are rendered from `dot_codex/AGENTS.md.tmpl`. Shared
workflow and style fragments live in `.chezmoitemplates/`; changing those fragments
also changes Claude instructions. Keep Codex-specific behavior in the Codex template.

`dot_codex/modify_private_config.toml.tmpl` merges the encrypted baseline with
runtime state. Keep project trust, hook trust, app permissions, and host-specific
state intact. Project `.codex/config.toml` files inherit the global approval policy;
keep integration definitions there without adding independent approval defaults.

`dot_codex/modify_hooks.json.tmpl` preserves unrelated handlers and enforces one
Moshi handler per managed event. Invalid JSON or invalid event containers must fail
without output. Herdr owns `~/.codex/herdr-agent-state.sh`. Do not replace its script
or hook when updating Moshi. Hook changes may require Codex's own trust review.
The source repository's `.codex/hooks.json` intentionally has no auto-commit hook.

`~/.codex/rules/default.rules` is runtime-owned. One-time approvals should not become
permanent cross-project policy. Do not synchronize accumulated approvals between
machines. Back up this file before removing obsolete entries.

For maintenance, check source Git status and chezmoi status, preview the intended
targets, apply only those targets, and verify there is no target drift. Do not apply
unrelated dotfiles or publish partially reviewed source changes.

For instruction changes, inspect `codex debug prompt-input` from each affected
checkout. Capture its output privately: it can contain local instructions and paths.
Check that required sections near the end are present. Keep concise requirements in
AGENTS.md and task-specific reference material in linked documents; do not solve
instruction truncation by increasing every session's context budget.

Start a new session after changing instructions or project configuration. Do not
assume an already running session has reloaded them.

References verified with Codex 0.154.0 and chezmoi 2.72.1 on 2026-09-16:

- [Instruction discovery](https://learn.chatgpt.com/docs/agent-configuration/agents-md)
- [Command rules](https://learn.chatgpt.com/docs/agent-configuration/rules)
- [Hooks](https://learn.chatgpt.com/docs/hooks)
- [Scoped chezmoi apply](https://www.chezmoi.io/reference/commands/apply/)
