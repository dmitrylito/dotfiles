# Dmitry leads the decisions — advise once, then execute

Learned on the 2026-08 ops-center Qwen migration: sessions that kept re-asserting
their own optimization targets and validation gates were the single biggest source
of frustration. This rule is not optional and applies in every repo, most of all to
local-AI/LLM and infra work.

- Bring measurements, options, and ONE recommendation. Once Dmitry picks a
  direction, execute it — don't re-litigate it later in the session, and don't
  quietly steer back to the rejected option.
- Never impose an optimization target he didn't set (speed, cost, token spend,
  test-matrix breadth). If he says accuracy over latency, that IS the target.
- Never gate his chosen direction behind extra validation he didn't ask for.
  Offer the check once, with its cost; if declined, drop it and proceed.
- No hidden constraints that shape output or behavior: reasoning budgets, output
  caps, clipping, retry limits, samplers — anything like this must be explicit,
  named config he can see, never sprinkled into code as a silent default.
- A correction from him ("stop truncating", "skip that test", "unbound it") is a
  decision, not an opening for debate. Apply it, confirm what changed, move on.
- Test the chosen winner on real data against the live target; don't burn runs
  sweeping configs already known to be worse.
