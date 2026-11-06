---
name: style-tuner
description: Tune Dmitry's output contract from evidence. Use when asked to improve how Claude writes, to review or adjust the style guard, when responses keep getting blocked or rewritten, or on a periodic check of the contract. Triggers - style guard, output contract, style-rules.md, "responses are too verbose", "stop blocking me", "tune the rules", "why did that get rewritten".
---

# Tune the output contract from evidence, not vibes

The contract lives in `~/.claude/hooks/style-rules.md`. `~/.claude/hooks/style-guard.py`
runs on Stop in `observe` mode: it records violations to the verdict log and writes nothing,
so tuning the rules is the ONLY way output changes. Never rewire it to block — see the
constraint at the bottom. That one file is the single source of truth: the Terse
output style includes it verbatim, so editing it changes the system prompt, and the Stop
hook judges against it. Never hand-edit `~/.claude/` — everything here is chezmoi-managed
under `~/.local/share/chezmoi/home/dot_claude/`.

## Run the miner first, always

```
python3 ~/.claude/skills/style-tuner/mine.py --days 30
```

It reports the clean rate, what fired and how often, and historical blocks recovered from
transcripts. Change nothing until you have read it — the point of this skill is that edits
are justified by counts, not by an impression of how a session felt.

## Decide from the numbers

- **One banned word dominates** — it is legitimate vocabulary in Dmitry's actual work.
  Remove it from `BANNED` in the hook and from rule 5 in `style-rules.md`, together.
- **`preamble` or `heading` recurs** — the regex is doing its job and the wording is not
  landing. Sharpen the rule text; do not widen the regex, which raises false positives on
  the narration background jobs are required to write.
- **`padding` recurs** — `closing_recap()` is catching real recaps and rule 1 is not landing.
  Sharpen the rule text before touching the 0.55 overlap threshold.
- **`ungrounded-path` recurs** — check several by hand first. Real fabricated paths mean rule
  3 needs teeth; paths that plainly exist mean `PATH_RE` is over-matching, or the response was
  proposing a file to create and `HEDGED` missed the phrasing.
- **Clean rate above ~95%** — leave the contract alone. A guard that never fires is working.

## Where each kind of change belongs

- Enforced wording, banned words, per-response shape → `home/dot_claude/hooks/style-rules.md`
- Detection logic, thresholds, new checks → `home/dot_claude/hooks/executable_style-guard.py`
- The prose version Dmitry reads, and anything about how to work rather than how to write →
  `home/dot_claude/rules/communication.md`
- Orientation only, never rules → `home/dot_claude/CLAUDE.md.tmpl`

`style-rules.md` and `rules/communication.md` say overlapping things on purpose and drift
apart if edited separately. Change both in the same pass.

## Before finishing

1. `python3 -c "import ast,pathlib; ast.parse(pathlib.Path('<hook>').read_text())"` after any
   hook edit.
2. Replay the cases the change was meant to affect — feed a synthetic Stop payload
   (`{"hook_event_name":"Stop","prompt_id":"t1","last_assistant_message":"..."}`) to
   `style-guard.py check` with `STYLE_GUARD_JUDGE=0`, and confirm both that the intended case
   now passes and that a case which should still block still blocks. Use a distinct
   `prompt_id` per case: the per-turn cap silently allows everything after the first block.
3. `chezmoi apply`, which commits and pushes to master.

## Two hard constraints

**Never make the Stop hook speak.** Blocking a response left three entries in the transcript
— the discarded text, the instruction, the rewrite — re-sent on every later turn with
autoCompact off, and no hook output field can delete a message. Warnings were no use either.
Dmitry decided on 2026-08-19 that Stop records and stays silent. `check`/`check-fast` still
implement blocking and are deliberately unwired.

**Never put an LLM call back on the Stop path.** A Haiku judge lived there once: ~10s on every
single response, and because it could only warn, the entire cost bought two findings that
`closing_recap()` and `ungrounded_paths()` now compute in ~16ms — and compute more accurately,
since they check the filesystem instead of guessing from a truncated excerpt. If a new check
cannot be written deterministically, it does not belong in the Stop hook.
