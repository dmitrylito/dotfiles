// Run with node --test scripts/test-opencode-statusline.mjs; no credentials/network needed.
import { test } from "node:test"
import assert from "node:assert/strict"
import { matchingAccounts, normalizeLimits, quotaText, fitStatusline, QUOTA_REFRESH_MS } from "../dot_config/opencode/statusline-data.mjs"

const token = (user) => `header.${Buffer.from(JSON.stringify({ "https://api.openai.com/auth": { chatgpt_user_id: user } })).toString("base64url")}.signature`

test("quota requires the same user as well as workspace, and OAuth authentication", () => {
  const openai = { type: "oauth", accountId: "workspace", access: token("user") }
  const codex = { tokens: { account_id: "workspace", access_token: token("user") } }
  assert.equal(matchingAccounts(openai, codex), true)
  assert.equal(matchingAccounts({ ...openai, accountId: "another" }, codex), false)
  assert.equal(matchingAccounts({ ...openai, access: token("another") }, codex), false)
  assert.equal(matchingAccounts({ ...openai, access: "invalid" }, codex), false)
  assert.equal(matchingAccounts({ ...openai, type: "api" }, codex), false)
  assert.equal(matchingAccounts({}, {}), false)
})

test("select Codex bucket and report only windows actually supplied", () => {
  const limits = normalizeLimits({
    rateLimits: { primary: { usedPercent: 80, windowDurationMins: 300 } },
    rateLimitsByLimitId: { codex: { primary: null, secondary: { usedPercent: 1, windowDurationMins: 10080 } } },
  })
  assert.deepEqual(limits.windows, [{ minutes: 10080, remaining: 99, resetsAt: null }])
  assert.equal(quotaText(limits, ""), "7d: 99% left")
  assert.throws(() => normalizeLimits({ rateLimits: { limitId: "spark", primary: { usedPercent: 0, windowDurationMins: 300 } } }))
  assert.throws(() => normalizeLimits({ rateLimits: { primary: { usedPercent: "bad", windowDurationMins: 300 } } }))
})

test("clamp remaining percentage and retain nonstandard window labels", () => {
  const quota = normalizeLimits({ rateLimits: { primary: { usedPercent: 110, windowDurationMins: 15 }, secondary: { usedPercent: -1, windowDurationMins: 300 } } })
  assert.equal(quotaText(quota, ""), "15m: 0% left | 5h: 100% left")
})

test("never invent remaining quota on errors, stale values, or elapsed reset", () => {
  const now = Date.now()
  const quota = { fetchedAt: now, windows: [{ minutes: 300, remaining: 82, resetsAt: Math.floor(now / 1000) + 100 }] }
  assert.equal(quotaText(null, "account mismatch"), "GPT quota: account mismatch")
  assert.equal(quotaText(null, "quota timeout"), "GPT quota: unavailable")
  assert.equal(quotaText(quota, "quota timeout", false, now), "5h: 82% left [stale]")
  assert.equal(quotaText(quota, "", false, now + QUOTA_REFRESH_MS * 3), "5h: ? left [stale]")
})

test("layout drops reset detail before PR/directory and preserves quotas at narrow widths", () => {
  const input = { directory: "backend", pr: "PR #123", quota: "5h: 82% left | 7d: 64% left", quotaFull: "5h: 82% left (resets 4:30 PM) | 7d: 64% left (resets Fri)", model: "GPT-6 Astra · medium | ctx: 23%" }
  const wide = fitStatusline({ ...input, width: 160 })
  assert.match(wide.left, /resets/)
  const medium = fitStatusline({ ...input, width: 85 })
  assert.doesNotMatch(medium.left, /resets/)
  assert.match(medium.left, /PR #123/)
  assert.equal(medium.right, input.model)
  const small = fitStatusline({ ...input, width: 60 })
  assert.equal(small.left, input.quota)
  assert.equal(small.right, input.model)
  const tiny = fitStatusline({ ...input, width: 40 })
  assert.equal(tiny.stacked, true)
  assert.equal(tiny.left, input.quota)
  assert.equal(tiny.right, input.model)
})
