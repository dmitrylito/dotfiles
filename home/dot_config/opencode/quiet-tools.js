// Quiet tool display defaults for OpenCode 1.18.31; register in tui.json.
// Uses the same persisted keys as the command palette; toggles still work in-session.
import { createEffect } from "solid-js"

export default {
  id: "dmitry.quiet-tools",
  tui: async (api) => {
    let applied = false
    createEffect(() => {
      if (!api.kv.ready || applied) return
      applied = true
      api.kv.set("tool_details_visibility", false)
      api.kv.set("generic_tool_output_visibility", false)
    })
  },
}
