// OpenCode statusline data and layout helpers. Imported by statusline.tsx.
// Quotas require matching local OpenCode/Codex ChatGPT logins and codex on PATH.
// Reads account limits only; never starts a model turn or exposes credentials.
import { readFile } from "node:fs/promises"
import { homedir } from "node:os"
import { join } from "node:path"
import { spawn, execFile } from "node:child_process"
import { promisify } from "node:util"

const exec = promisify(execFile)
export const QUOTA_REFRESH_MS = 300_000
export const PR_REFRESH_MS = 300_000
export const REQUEST_TIMEOUT_MS = 15_000
const MAX_OUTPUT_BYTES = 262_144

function claims(token) {
  try {
    return JSON.parse(Buffer.from(token.split(".")[1], "base64url").toString())
  } catch {
    return {}
  }
}

export function matchingAccounts(openai, codex) {
  if (openai?.type !== "oauth" || !openai.accountId || openai.accountId !== codex?.tokens?.account_id) return false
  const left = claims(openai.access)["https://api.openai.com/auth"]?.chatgpt_user_id
  const right = claims(codex.tokens.access_token)["https://api.openai.com/auth"]?.chatgpt_user_id
  return Boolean(left && right && left === right)
}

async function accountsMatch() {
  try {
    const [openai, codex] = await Promise.all([
      readFile(join(process.env.XDG_DATA_HOME || join(homedir(), ".local/share"), "opencode/auth.json"), "utf8"),
      readFile(join(process.env.CODEX_HOME || join(homedir(), ".codex"), "auth.json"), "utf8"),
    ])
    return matchingAccounts(JSON.parse(openai).openai, JSON.parse(codex))
  } catch {
    return false
  }
}

export function normalizeLimits(result) {
  const bucket = result.rateLimitsByLimitId?.codex ?? result.rateLimits
  if (!bucket || (bucket.limitId && bucket.limitId !== "codex")) throw new Error("quota unavailable")
  const windows = [bucket.primary, bucket.secondary].filter((item) =>
    item && Number.isFinite(item.usedPercent) && Number.isFinite(item.windowDurationMins) && item.windowDurationMins > 0,
  ).map((item) => ({
    minutes: item.windowDurationMins,
    remaining: Math.max(0, Math.min(100, Math.round(100 - item.usedPercent))),
    resetsAt: Number.isFinite(item.resetsAt) ? item.resetsAt : null,
  }))
  if (!windows.length) throw new Error("quota unavailable")
  return { windows, fetchedAt: Date.now() }
}

export async function readQuota(signal) {
  if (!(await accountsMatch())) throw new Error("account mismatch")
  if (signal?.aborted) throw new Error("cancelled")
  const result = await new Promise((resolve, reject) => {
    const child = spawn("codex", ["app-server"], {
      cwd: homedir(),
      stdio: ["pipe", "pipe", "ignore"],
    })
    let buffer = ""
    let bytes = 0
    let settled = false
    const finish = (error, value) => {
      if (settled) return
      settled = true
      clearTimeout(timeout)
      signal?.removeEventListener("abort", abort)
      child.stdin.end()
      child.kill("SIGTERM")
      const kill = setTimeout(() => child.kill("SIGKILL"), 1000)
      kill.unref()
      child.once("close", () => clearTimeout(kill))
      if (error) reject(error)
      else resolve(value)
    }
    const abort = () => finish(new Error("cancelled"))
    const timeout = setTimeout(() => finish(new Error("quota timeout")), REQUEST_TIMEOUT_MS)
    signal?.addEventListener("abort", abort, { once: true })
    const send = (message) => child.stdin.write(JSON.stringify(message) + "\n")
    child.on("error", () => finish(new Error("codex unavailable")))
    child.stdin.on("error", () => finish(new Error("quota unavailable")))
    child.on("exit", () => finish(new Error("quota unavailable")))
    child.stdout.on("data", (data) => {
      bytes += data.length
      if (bytes > MAX_OUTPUT_BYTES) return finish(new Error("quota output limit"))
      buffer += data.toString()
      let newline
      while (!settled && (newline = buffer.indexOf("\n")) !== -1) {
        const line = buffer.slice(0, newline)
        buffer = buffer.slice(newline + 1)
        let message
        try { message = JSON.parse(line) } catch { continue }
        if (message.error && (message.id === 1 || message.id === 2)) return finish(new Error("quota unavailable"))
        if (message.id === 1) {
          send({ method: "initialized", params: {} })
          send({ method: "account/rateLimits/read", id: 2, params: {} })
        }
        if (message.id === 2) finish(null, message.result)
      }
    })
    send({ method: "initialize", id: 1, params: { clientInfo: { name: "opencode_statusline", version: "1.0.0" } } })
  })
  // Recheck after the RPC so an account switch cannot display another account's quota.
  if (!(await accountsMatch())) throw new Error("account mismatch")
  return normalizeLimits(result)
}

export async function readPullRequest(directory, signal) {
  try {
    const { stdout } = await exec("gh", ["pr", "view", "--json", "number,state", "--jq", 'select(.state == "OPEN") | .number'], {
      cwd: directory, timeout: 5000, maxBuffer: 8192, signal,
    })
    return /^\d+$/.test(stdout.trim()) ? `PR #${stdout.trim()}` : ""
  } catch {
    return ""
  }
}

function windowName(minutes) {
  if (minutes % 1440 === 0) return `${minutes / 1440}d`
  if (minutes % 60 === 0) return `${minutes / 60}h`
  return `${minutes}m`
}

export function quotaText(quota, error, detailed = false, now = Date.now()) {
  if (!quota) return error === "account mismatch" ? "GPT quota: account mismatch" : `GPT quota: ${error ? "unavailable" : "loading"}`
  const stale = Boolean(error) || now - quota.fetchedAt > QUOTA_REFRESH_MS * 2
  const text = quota.windows.map((window) => {
    const expired = window.resetsAt && window.resetsAt * 1000 <= now
    const value = `${windowName(window.minutes)}: ${expired ? "?" : window.remaining + "%"} left`
    if (!detailed || !window.resetsAt || expired) return value
    const reset = new Date(window.resetsAt * 1000).toLocaleString("en-US", {
      ...(window.minutes >= 1440 ? { weekday: "short" } : {}),
      hour: "numeric", minute: "2-digit", hour12: true,
    })
    return `${value} (resets ${reset})`
  }).join(" | ")
  return text + (stale ? " [stale]" : "")
}

export function fitStatusline({ directory, pr = "", quota = "", quotaFull = quota, model, width }) {
  const joinParts = (...parts) => parts.filter(Boolean).join(" | ")
  const right = model || ""
  const candidates = [joinParts(directory, pr, quotaFull), joinParts(directory, pr, quota), joinParts(directory, quota), quota]
  for (const left of candidates) {
    if (left.length + right.length + 2 <= width) return { left, right }
  }
  // At very small widths use two rows rather than silently losing a quota window.
  return { left: quota || directory, right, stacked: true }
}
