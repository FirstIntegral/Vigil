import QtQuick
import Quickshell
import Quickshell.Io

// Headless collector host. Polls bin/vigil snapshot and exposes one
// stable model to the bar widget and panel. All process policy lives
// in the Python collector so this file does not invent pids.
Item {
  id: root

  property var shell: null
  property var settings: ({})

  property bool ready: false
  property bool loading: false
  property string state: "loading"
  property string message: "Scanning agents…"
  property string generatedAt: ""
  property string hostName: ""
  property var sessions: []
  property int sessionsRevision: 0
  property int agentCount: 0
  property int runningCount: 0
  property int waitingCount: 0
  property var todayUsd: null
  property var pending: []
  property bool frozen: false
  property string mode: "seatbelt"
  property string alert: "both"
  property string severity: "ok"
  property string alertLine: ""
  property string trustUntil: ""
  property var dossier: ({})
  property bool grokHook: false
  property bool claudeHook: false
  property bool opencodeHook: false
  property bool codexHook: false
  property bool incident: false
  property var lid: ({ enabled: true, locked: false, held: false })
  property var audit: []
  property var tickets: ({ allow: [], deny: [] })
  property var folders: []
  property bool trustUntilLock: false
  property string _stdout: ""
  property string _stderr: ""
  property string lastError: ""
  property string killStatus: ""
  property int pendingKillPid: 0
  property bool pendingKillAll: false

  readonly property int refreshIntervalSec: {
    var value = parseInt(String(setting("refreshIntervalSec", 2)), 10)
    if (!isFinite(value)) value = 2
    return Math.max(1, Math.min(30, value))
  }

  readonly property string glyph: {
    if (root.incident || root.frozen || root.severity === "critical") return "󰀪"
    if (root.severity === "warning" || root.waitingCount > 0) return "󰀦"
    return "󰈈"
  }
  readonly property string barLabel: {
    if (!root.ready) return "…"
    if (root.incident) return "INCIDENT"
    if (root.frozen) return "FROZEN"
    if (root.alertLine) {
      var line = root.alertLine
      return line.length > 36 ? line.slice(0, 33) + "…" : line
    }
    if (root.mode === "off") return "off"
    if (root.mode === "ask") return "ask"
    return String(root.agentCount)
  }
  readonly property bool alarming: root.waitingCount > 0 || root.frozen || root.severity === "critical" || root.incident
  readonly property bool hasAgents: root.agentCount > 0
  readonly property bool hooksLive: root.grokHook || root.claudeHook || root.opencodeHook || root.codexHook

  function setting(name, fallback) {
    var value = settings ? settings[name] : undefined
    return value === undefined || value === null ? fallback : value
  }

  function helperPath() {
    return decodeURIComponent(Qt.resolvedUrl("bin/vigil").toString().replace(/^file:\/\//, ""))
  }

  function refresh() {
    if (fetchProcess.running) return
    loading = true
    _stdout = ""
    _stderr = ""
    fetchProcess.command = [helperPath(), "snapshot"]
    fetchProcess.running = true
  }

  function apply(raw) {
    try {
      var data = JSON.parse(String(raw || ""))
      if (Number(data.schemaVersion) !== 1) {
        state = "error"
        message = "Vigil collector returned an unknown snapshot schema."
        return
      }
      generatedAt = String(data.generatedAt || "")
      hostName = String(data.host || "")
      sessions = Array.isArray(data.sessions) ? data.sessions : []
      pending = Array.isArray(data.pending) ? data.pending : []
      frozen = data.frozen === true
      mode = String(data.mode || "seatbelt")
      alert = String(data.alert || "both")
      trustUntil = String(data.trustUntil || "")
      dossier = data.dossier || {}
      if (pending.length > 0) {
        alertLine = String(pending[0].barLine || "")
        severity = String(pending[0].severity || "warning")
      } else {
        alertLine = ""
        severity = "ok"
      }
      audit = Array.isArray(data.audit) ? data.audit : []
      tickets = data.tickets || { allow: [], deny: [] }
      folders = Array.isArray(data.folders) ? data.folders : []
      trustUntilLock = data.trustUntilLock === true
      var hooks = data.hooks || {}
      grokHook = hooks.grok === true
      claudeHook = hooks.claude === true
      opencodeHook = hooks.opencode === true
      codexHook = hooks.codex === true
      incident = data.incident === true
      lid = data.lid || { enabled: true, locked: false, held: false }
      sessionsRevision++
      var totals = data.totals || {}
      agentCount = Number(totals.agents) || sessions.length
      runningCount = Number(totals.running) || 0
      waitingCount = Number(totals.waiting) || pending.length
      todayUsd = totals.todayUsd === undefined ? null : totals.todayUsd
      ready = true
      state = "ready"
      if (incident) message = "Incident. Unlock does not unfreeze."
      else if (frozen) message = "Frozen. Every tool call is denied."
      else if (waitingCount > 0) message = waitingCount + " approval" + (waitingCount === 1 ? "" : "s") + " waiting."
      else if (agentCount === 0) message = "No coding agents running."
      else message = ""
      lastError = ""
    } catch (error) {
      state = "error"
      message = "Vigil returned an unreadable snapshot."
      lastError = String(error)
    }
  }

  function sessionByPid(pid) {
    var want = Number(pid)
    for (var i = 0; i < sessions.length; i++) {
      if (Number(sessions[i].pid) === want) return sessions[i]
    }
    return null
  }

  function requestKill(pid) {
    pendingKillAll = false
    pendingKillPid = Number(pid) || 0
    if (pendingKillPid <= 1) {
      pendingKillPid = 0
      return
    }
    var row = sessionByPid(pendingKillPid)
    killStatus = row
      ? "Kill " + row.displayName + " pid " + pendingKillPid + "? Enter confirms."
      : "Kill pid " + pendingKillPid + "? Enter confirms."
  }

  function requestKillAll() {
    pendingKillPid = 0
    pendingKillAll = true
    killStatus = "Kill every coding agent on this machine? Enter confirms."
  }

  function cancelKill() {
    pendingKillPid = 0
    pendingKillAll = false
    killStatus = ""
  }

  function confirmKill() {
    if (killProcess.running) return
    if (pendingKillAll) {
      killProcess.command = [helperPath(), "kill-all", "--yes"]
      killStatus = "Signalling every agent…"
    } else if (pendingKillPid > 1) {
      killProcess.command = [helperPath(), "kill", String(pendingKillPid)]
      killStatus = "Signalling pid " + pendingKillPid + "…"
    } else {
      return
    }
    killProcess.running = true
  }

  function decide(id, action) {
    actionProc.command = [helperPath(), "decide", String(id), String(action)]
    actionProc.running = true
  }

  function freeze() {
    actionProc.command = [helperPath(), "freeze"]
    actionProc.running = true
  }

  function unfreeze() {
    actionProc.command = [helperPath(), "unfreeze"]
    actionProc.running = true
  }

  function panic() {
    actionProc.command = [helperPath(), "panic", "--yes"]
    actionProc.running = true
  }

  function installHooks() {
    actionProc.command = [helperPath(), "install", "--helper", helperPath()]
    actionProc.running = true
  }

  function cycleMode() {
    actionProc.command = [helperPath(), "mode", "cycle"]
    actionProc.running = true
  }

  function setMode(name) {
    actionProc.command = [helperPath(), "mode", String(name)]
    actionProc.running = true
  }

  function cycleAlert() {
    actionProc.command = [helperPath(), "alert", "cycle"]
    actionProc.running = true
  }

  function trustHour() {
    actionProc.command = [helperPath(), "trust", "60"]
    actionProc.running = true
  }

  function cycleEnvelope(passportId) {
    if (!passportId) return
    actionProc.command = [helperPath(), "envelope", String(passportId), "cycle"]
    actionProc.running = true
  }

  function rewindProject(rootPath) {
    var args = [helperPath(), "rewind"]
    if (rootPath) args.push("--root", String(rootPath))
    actionProc.command = args
    actionProc.running = true
  }

  function cycleLid() {
    actionProc.command = [helperPath(), "lid", "cycle"]
    actionProc.running = true
  }

  function revokeTicket(key) {
    if (!key) return
    actionProc.command = [helperPath(), "tickets", "revoke", String(key)]
    actionProc.running = true
  }

  function setFolder(path, envelope) {
    if (!path) return
    var env = envelope ? String(envelope) : "project"
    actionProc.command = [helperPath(), "folder", String(path), env]
    actionProc.running = true
  }

  function trustUntilLockScreen() {
    actionProc.command = [helperPath(), "trust", "--until-lock"]
    actionProc.running = true
  }

  visible: false

  Timer {
    interval: root.refreshIntervalSec * 1000
    repeat: true
    running: true
    triggeredOnStart: true
    onTriggered: root.refresh()
  }

  Timer {
    id: killStatusTimer
    interval: 2500
    repeat: false
    onTriggered: {
      if (!root.pendingKillPid && !root.pendingKillAll)
        root.killStatus = ""
    }
  }

  Process {
    id: fetchProcess
    running: false
    command: []
    onExited: function(exitCode) {
      root.loading = false
      var stdout = String(output.text || root._stdout || "")
      var stderr = String(errors.text || root._stderr || "").trim()
      if (stdout.trim() !== "") {
        root.apply(stdout)
      } else {
        root.state = "error"
        root.message = stderr !== "" ? stderr : "Vigil collector failed."
      }
    }
    stdout: StdioCollector {
      id: output
      waitForEnd: true
      onStreamFinished: root._stdout = text
    }
    stderr: StdioCollector {
      id: errors
      waitForEnd: true
      onStreamFinished: root._stderr = text
    }
  }

  Process {
    id: killProcess
    running: false
    command: []
    onExited: function(exitCode) {
      var raw = String(killOut.text || "")
      var payload = null
      try { payload = JSON.parse(raw) } catch (error) { payload = null }
      root.pendingKillPid = 0
      root.pendingKillAll = false
      if (exitCode === 0 && payload && payload.ok) {
        root.killStatus = payload.agent
          ? "Signalled " + payload.agent + " pid " + payload.pid + "."
          : "Signalled."
      } else {
        var err = payload && payload.error ? String(payload.error) : String(killErr.text || "kill refused")
        root.killStatus = err
      }
      killStatusTimer.restart()
      Qt.callLater(root.refresh)
    }
    stdout: StdioCollector {
      id: killOut
      waitForEnd: true
    }
    stderr: StdioCollector {
      id: killErr
      waitForEnd: true
    }
  }

  Process {
    id: actionProc
    running: false
    command: []
    onExited: Qt.callLater(root.refresh)
  }
}
