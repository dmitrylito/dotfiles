# Judge every subagent spawn on its merits — then act, don't ask

A subagent starts cold: it re-pays the full system prompt, CLAUDE.md, every file in
`rules/`, and the skill/tool listings before it does a single useful thing. That fixed cost
routinely exceeds a small lookup done inline, where the same context is already cached and
free. So neither default is correct — apply the test below and commit to the answer. Never
ask permission for a spawn that clears the bar, and never narrate one you ruled out.

## The test: does delegating spare me from reading material I'd then throw away?

Spawn when yes:

- Wide or unknown search space — roughly 5+ files, or "find which of these does X".
- The useful output is a short verdict distilled from noisy input (log trawls, grep sweeps).
- Several genuinely independent questions — spawn them in ONE message so they overlap.

Stay inline when no:

- I already know the file, symbol, or command, or it's ≤3 tool calls.
- I need the raw content, not a digest — a summary is lossy and I'd have to re-read anyway.
- One command settles it: a version, a flag, a config value, whether it compiles.
- The answer must be exact. Every summarizing hop is a chance to garble it.

## Make the spawns that pass as cheap as they can be

- Mechanical location, zero judgement → `lookup` (haiku) only when the user has
  approved using a cheaper model; otherwise preserve the chosen model quality.
- Wide read-only exploration where I want the conclusion → `Explore`.
- Reserve main-model-inheriting agents for work that actually needs reasoning.
- One well-scoped agent beats three overlapping ones. Give each a specific question, not a
  topic, and say what shape the answer should take.
