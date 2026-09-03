// OpenCode global plugin. install() rewrites __VIGIL_HELPER__.
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
      timeout: eventName === "post_tool_use" ? 5000 : 120000,
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
  if (result.error || result.status !== 0 || decision === "deny" || decision === "") {
    const reason =
      parsed.reason || specific.permissionDecisionReason || "Vigil denied the call."
    throw new Error(reason)
  }
}

export const VigilSeatbelt = async ({ directory }) => {
  return {
    "tool.execute.before": async (input, output) => {
      runGate("pre_tool_use", input.tool, output.args, input.sessionID, directory)
    },
    "tool.execute.after": async (input, output) => {
      try {
        runGate(
          "post_tool_use",
          input.tool,
          output.args || {},
          input.sessionID,
          directory,
        )
      } catch {
        // Post cannot undo. Gate still logs.
      }
    },
  }
}
