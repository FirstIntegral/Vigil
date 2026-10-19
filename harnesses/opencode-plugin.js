// OpenCode global plugin. install() rewrites __VIGIL_HELPER__.
// V2: default export { id, setup }, hooks registered on ctx.tool.
// V1: named VigilSeatbelt function export with the legacy hook map.
// tool.execute.before: spawn vigil gate; throw on deny. Fail closed.

import { spawnSync } from "node:child_process"

const HELPER = "__VIGIL_HELPER__"

function runGate(eventName, tool, args, sessionId, directory) {
  const payload = JSON.stringify({
    hookEventName: eventName,
    sessionId: sessionId || "",
    cwd: directory || "",
    workspaceRoot: directory || "",
    toolName: tool || "",
    toolInput: args && typeof args === "object" ? args : {},
  })
  let result
  try {
    result = spawnSync(HELPER, ["gate"], {
      input: payload,
      encoding: "utf8",
      timeout: eventName === "post_tool_use" ? 5000 : __VIGIL_HOOK_TIMEOUT_MS__,
      maxBuffer: 1024 * 1024,
    })
  } catch {
    throw new Error("Vigil could not run the gate.")
  }
  let parsed = {}
  try {
    parsed = JSON.parse((result.stdout || "").trim() || "{}")
  } catch {
    parsed = {}
  }
  const specific = parsed.hookSpecificOutput || {}
  const decision = String(parsed.decision || specific.permissionDecision || "").toLowerCase()
  const isPost = eventName === "post_tool_use" || eventName === "PostToolUse"
  if (isPost) {
    // Post cannot undo. Empty JSON is a quiet log (Grok rejects "allow" here).
    if (decision === "deny" || decision === "block") {
      const reason =
        parsed.reason || specific.permissionDecisionReason || "Vigil denied the call."
      throw new Error(reason)
    }
    return
  }
  if (result.error || result.status !== 0 || decision === "deny" || decision === "") {
    const reason =
      parsed.reason || specific.permissionDecisionReason || "Vigil denied the call."
    throw new Error(reason)
  }
}

function gateHooks(directory) {
  return {
    "tool.execute.before": async (input, output) => {
      runGate("pre_tool_use", input.tool, output.args, input.sessionID, directory)
    },
    "tool.execute.after": async (input, output) => {
      try {
        runGate("post_tool_use", input.tool, output.args || {}, input.sessionID, directory)
      } catch {
        // Post cannot undo. Gate still logs.
      }
    },
  }
}

// OpenCode V2 plugin API.
export default {
  id: "brwsk.vigil",
  async setup(ctx) {
    const directory = ctx.location.directory
    await ctx.tool.hook("execute.before", (event) => {
      runGate("pre_tool_use", event.tool, event.input, event.sessionID, directory)
    })
    await ctx.tool.hook("execute.after", (event) => {
      try {
        runGate("post_tool_use", event.tool, event.input, event.sessionID, directory)
      } catch {
        // Post cannot undo. Gate still logs.
      }
    })
  },
}

// OpenCode V1 plugin API.
export const VigilSeatbelt = async ({ directory }) => gateHooks(directory)
