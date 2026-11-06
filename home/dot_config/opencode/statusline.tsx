/** @jsxImportSource @opentui/solid */
// Claude/Codex-style footer for OpenCode 1.18.31+. Register in tui.json.
// Quota reads run every five minutes without model calls; timers stop on disposal.
import { createMemo, createSignal, Show } from "solid-js"
import { useTerminalDimensions } from "@opentui/solid"
import { basename } from "node:path"
import { readQuota, readPullRequest, quotaText, fitStatusline, QUOTA_REFRESH_MS, PR_REFRESH_MS } from "./statusline-data.mjs"

export default {
  id: "dmitry.statusline",
  tui: async (api) => {
    const [quota, setQuota] = createSignal(null)
    const [error, setError] = createSignal("")
    const [pr, setPr] = createSignal({ key: "", value: "" })
    const [clock, setClock] = createSignal(Date.now())
    let pending = false
    let nextQuota = 0
    let nextPr = 0
    let prPending = false
    const refresh = async () => {
      if (pending || Date.now() < nextQuota || api.lifecycle.signal.aborted) return
      pending = true
      nextQuota = Date.now() + QUOTA_REFRESH_MS
      try {
        const value = await readQuota(api.lifecycle.signal)
        if (!api.lifecycle.signal.aborted) { setQuota(value); setError("") }
      } catch (error) {
        if (!api.lifecycle.signal.aborted) {
          if (error.message === "account mismatch") setQuota(null)
          setError(error.message)
        }
      } finally { pending = false }
    }
    const refreshPr = async () => {
      const directory = api.state.path.directory
      const branch = api.state.vcs?.branch
      const key = `${directory}:${branch}`
      if (!directory || !branch || prPending || (pr().key === key && Date.now() < nextPr)) return
      prPending = true
      nextPr = Date.now() + PR_REFRESH_MS
      setPr({ key, value: "" })
      try {
        const value = await readPullRequest(directory, api.lifecycle.signal)
        if (!api.lifecycle.signal.aborted) setPr({ key, value })
      } finally { prPending = false }
    }
    const tick = () => { setClock(Date.now()); void refresh(); void refreshPr() }
    const timer = setInterval(tick, 5000)
    api.lifecycle.onDispose(() => clearInterval(timer))
    tick()

    function Statusline() {
      const dimensions = useTerminalDimensions()
      const sessionID = () => api.route.current.name === "session" ? api.route.current.params?.sessionID : undefined
      const messages = () => sessionID() ? api.state.session.messages(sessionID()) : []
      const model = createMemo(() => {
        const user = messages().findLast((message) => message.role === "user")
        const assistant = messages().findLast((message) => message.role === "assistant")
        const configured = api.state.config.model?.split("/") ?? []
        const providerID = user?.model?.providerID ?? assistant?.providerID ?? configured[0]
        const modelID = user?.model?.modelID ?? assistant?.modelID ?? configured.slice(1).join("/")
        const info = api.state.provider.find((provider) => provider.id === providerID)?.models[modelID]
        const variant = user?.variant
        const options = api.state.config.provider?.[providerID]?.models?.[modelID]?.options
        const effort = (variant && variant !== "default" ? info?.variants?.[variant]?.reasoningEffort ?? variant : options?.reasoningEffort) ?? ""
        const name = (info?.name || modelID || "No model").replace(/\s*\([^)]*context[^)]*\)/i, "")
        const last = messages().findLast((message) => message.role === "assistant" && message.tokens.output > 0)
        const contextModel = last && api.state.provider.find((provider) => provider.id === last.providerID)?.models[last.modelID]
        const tokens = last && last.tokens
        const used = tokens && contextModel?.limit.context
          ? Math.round((tokens.input + tokens.output + tokens.reasoning + tokens.cache.read + tokens.cache.write) / contextModel.limit.context * 100)
          : null
        return { providerID, text: `${name}${effort ? ` · ${effort}` : ""} | ctx: ${used === null ? "—" : `${used}%`}` }
      })
      const layout = createMemo(() => {
        const directory = api.state.path.directory
        const key = `${directory}:${api.state.vcs?.branch}`
        const showQuota = model().providerID === "openai"
        return fitStatusline({
          directory: basename(directory || ""),
          pr: pr().key === key ? pr().value : "",
          quota: showQuota ? quotaText(quota(), error(), false, clock()) : "",
          quotaFull: showQuota ? quotaText(quota(), error(), true, clock()) : "",
          model: model().text,
          width: Math.max(1, dimensions().width - 4),
        })
      })
      return <Show when={api.route.current.name === "session" || api.route.current.name === "home"}>
        <box paddingLeft={2} paddingRight={2} flexShrink={0} flexDirection={layout().stacked ? "column" : "row"} justifyContent="space-between">
          <text fg={error() ? api.theme.current.warning : api.theme.current.textMuted}>{layout().left}</text>
          <text fg={api.theme.current.textMuted}>{layout().right}</text>
        </box>
      </Show>
    }
    api.slots.register({ slots: { app_bottom: () => <Statusline /> } })
  },
}
