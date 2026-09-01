import QtQuick
import QtQuick.Controls
import Quickshell
import qs.Commons
import qs.Ui

// Ops panel: every live coding agent, a two-step kill, keyboard-first.
Panel {
  id: root
  moduleName: "xyz.brwsk.vigil"

  property var anchorItem: null
  property var hostWidget: null
  readonly property var barIdentity: hostWidget || root
  readonly property var service: bar && bar.shell ? bar.shell.serviceFor("xyz.brwsk.vigil") : null
  readonly property bool serviceReady: service && service.ready === true
  readonly property var sessions: service ? service.sessions : []
  readonly property int sessionsRevision: service ? service.sessionsRevision : 0
  readonly property int agentCount: service ? service.agentCount : 0
  readonly property int waitingCount: service ? service.waitingCount : 0
  readonly property bool frozen: service ? service.frozen === true : false
  readonly property string mode: service ? String(service.mode || "seatbelt") : "seatbelt"
  readonly property string alert: service ? String(service.alert || "both") : "both"
  readonly property var dossier: service && service.dossier ? service.dossier : ({})
  readonly property bool hooksLive: service ? service.hooksLive === true : false
  readonly property var pending: service && service.pending ? service.pending : []
  readonly property string killStatus: service ? service.killStatus : ""
  readonly property bool pendingKill: service && (service.pendingKillPid > 0 || service.pendingKillAll)
  readonly property bool incident: service ? service.incident === true : false
  readonly property var lid: service && service.lid ? service.lid : ({})

  property int selectedIndex: 0

  readonly property color contentForeground: bar ? bar.foreground : Color.foreground
  readonly property string contentFontFamily: bar ? bar.fontFamily : Style.font.family
  readonly property color surfaceColor: bar ? bar.background : Color.background

  onSessionsRevisionChanged: {
    if (root.selectedIndex >= root.sessions.length)
      root.selectedIndex = Math.max(0, root.sessions.length - 1)
  }

  function open() { root.controller.show() }
  function close() { root.controller.hide() }
  function toggle() {
    if (root.opened) root.close()
    else root.open()
  }
  function switchPanel(direction) {
    if (root.bar && typeof root.bar.switchPanelFrom === "function")
      return root.bar.switchPanelFrom(root.barIdentity, direction)
    return false
  }

  function selectedSession() {
    if (root.selectedIndex < 0 || root.selectedIndex >= root.sessions.length)
      return null
    return root.sessions[root.selectedIndex]
  }

  function moveSelection(delta) {
    if (root.sessions.length === 0) return
    var next = root.selectedIndex + delta
    if (next < 0) next = 0
    if (next > root.sessions.length - 1) next = root.sessions.length - 1
    root.selectedIndex = next
  }

  function openCwd() {
    var row = root.selectedSession()
    if (!row || !row.cwd) return
    Quickshell.execDetached(["xdg-open", String(row.cwd)])
  }

  function handleTextKey(t) {
    if (root.pendingKill) {
      if (t === "\r" || t === "\n" || t === "y" || t === "Y") {
        root.service.confirmKill()
        return
      }
      if (t === "n" || t === "N" || t === "Escape") {
        root.service.cancelKill()
        return
      }
    }
    if (t === "j" || t === "J") root.moveSelection(1)
    else if (t === "k" || t === "K") root.moveSelection(-1)
    else if (t === "r" || t === "R") { if (root.service) root.service.refresh() }
    else if (t === "o" || t === "O" || t === "\r" || t === "\n") root.openCwd()
    else if (t === "x" || t === "X") {
      var row = root.selectedSession()
      if (row && root.service) root.service.requestKill(row.pid)
    }
    else if (t === "a" || t === "A") {
      if (root.service && root.agentCount > 0) root.service.requestKillAll()
    }
    else if (t === "f" || t === "F") {
      if (!root.service) return
      if (root.frozen) root.service.unfreeze()
      else root.service.freeze()
    }
    else if (t === "p" || t === "P") {
      if (root.service) root.service.panic()
    }
    else if (t === "i" || t === "I") {
      if (root.service) root.service.installHooks()
    }
    else if (t === "m" || t === "M") {
      if (root.service) root.service.cycleMode()
    }
    else if (t === "t" || t === "T") {
      if (root.service) root.service.cycleAlert()
    }
    else if (t === "h" || t === "H") {
      if (root.service) root.service.trustHour()
    }
    else if (t === "e" || t === "E") {
      var row = root.selectedSession()
      if (row && root.service) root.service.cycleEnvelope(row.passportId || row.id)
    }
    else if (t === "w" || t === "W") {
      var row = root.selectedSession()
      var cwd = row && row.cwd ? row.cwd : ""
      if (root.service) root.service.rewindProject(cwd)
    }
    else if (t === "l" || t === "L") {
      if (root.service) root.service.cycleLid()
    }
    else if (t === "y" || t === "Y") {
      if (root.pending.length && root.service)
        root.service.decide(root.pending[0].id, "allow")
    }
    else if (t === "n" || t === "N") {
      if (root.pending.length && root.service)
        root.service.decide(root.pending[0].id, "deny")
    }
  }

  function rssLabel(bytes) {
    var n = Number(bytes) || 0
    if (n < 1024) return n + " B"
    if (n < 1024 * 1024) return Math.round(n / 1024) + " KB"
    return (n / (1024 * 1024)).toFixed(1) + " MB"
  }

  KeyboardPanel {
    id: panel
    anchorItem: root.anchorItem
    owner: root.barIdentity
    bar: root.bar
    open: root.opened
    focusTarget: keyCatcher
    contentWidth: panel.fittedContentWidth(Style.space(380))
    contentHeight: panel.fittedContentHeight(panelColumn.implicitHeight, Style.space(420))

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      clip: true
      onCloseRequested: {
        if (root.pendingKill && root.service) root.service.cancelKill()
        else root.close()
      }
      onTabRequested: function(direction) { root.switchPanel(direction) }
      onMoveRequested: function(dx, dy) {
        if (dy < 0) root.moveSelection(1)
        if (dy > 0) root.moveSelection(-1)
      }
      onTextKey: function(t) { root.handleTextKey(t) }

      Column {
        id: panelColumn
        width: parent.width
        spacing: Style.space(10)

        Item {
          width: parent.width
          implicitHeight: Math.max(heroIcon.implicitHeight, heroLabels.implicitHeight)

          Text {
            id: heroIcon
            text: root.service ? root.service.glyph : "󰈈"
            color: root.waitingCount > 0 ? Color.accent : root.contentForeground
            font.family: root.contentFontFamily
            font.pixelSize: Style.fontPx(2.4)
            anchors.left: parent.left
            anchors.top: parent.top
            anchors.topMargin: -Style.space(4)
          }

          Column {
            id: heroLabels
            anchors.left: heroIcon.right
            anchors.leftMargin: Style.space(14)
            anchors.right: parent.right
            anchors.top: parent.top
            spacing: 0

            Text {
              text: root.incident
                ? "Incident"
                : (root.frozen
                ? "Frozen"
                : (root.waitingCount > 0
                  ? (root.waitingCount + (root.waitingCount === 1 ? " waiting" : " waiting"))
                  : (root.agentCount === 0
                    ? "No agents"
                    : (root.agentCount + (root.agentCount === 1 ? " agent" : " agents")))))
              color: root.contentForeground
              font.family: root.contentFontFamily
              font.pixelSize: Style.fontPx(1.4)
              font.bold: true
              elide: Text.ElideRight
              width: parent.width
            }

            Text {
              text: {
                if (!root.serviceReady) return "scanning…"
                if (!root.hooksLive) return "hooks off · press i to arm"
                if (root.incident) return "U unfreeze · W rewind · N stay frozen"
                if (root.mode === "off") return "off · nothing is held · m cycles"
                if (root.frozen) return "frozen · every tool call denied"
                if (root.mode === "ask") return "ask · risky calls wait for you"
                if (root.waitingCount > 0) return "Y allow · N deny · A ticket"
                return "seatbelt · deadly only · alerts:" + root.alert
              }
              color: Qt.darker(root.contentForeground, 1.4)
              font.family: root.contentFontFamily
              font.pixelSize: Style.font.caption
              font.bold: true
              elide: Text.ElideRight
              width: parent.width
            }
          }
        }

        Text {
          visible: root.killStatus !== ""
          text: root.killStatus
          color: root.pendingKill ? Color.accent : root.contentForeground
          font.family: root.contentFontFamily
          font.pixelSize: Style.font.caption
          wrapMode: Text.Wrap
          width: parent.width
        }

        Repeater {
          model: root.pending
          Rectangle {
            required property var modelData
            width: panelColumn.width
            implicitHeight: pendCol.implicitHeight + Style.space(12)
            radius: Style.space(6)
            color: Qt.rgba(root.contentForeground.r, root.contentForeground.g, root.contentForeground.b, 0.06)
            border.color: Qt.rgba(root.contentForeground.r, root.contentForeground.g, root.contentForeground.b, 0.08)
            border.width: 1
            Column {
              id: pendCol
              anchors.left: parent.left
              anchors.right: parent.right
              anchors.leftMargin: Style.space(10)
              anchors.rightMargin: Style.space(10)
              anchors.top: parent.top
              anchors.topMargin: Style.space(6)
              spacing: Style.space(2)
              Text {
                text: String(modelData.title || "Approval needed")
                color: root.contentForeground
                font.family: root.contentFontFamily
                font.pixelSize: Style.font.bodySmall
                font.bold: true
                wrapMode: Text.Wrap
                width: parent.width
              }
              Text {
                text: String(modelData.summary || "")
                color: root.contentForeground
                opacity: 0.65
                font.family: root.contentFontFamily
                font.pixelSize: Style.font.caption
                wrapMode: Text.Wrap
                width: parent.width
              }
            }
          }
        }

        PanelSeparator {
          width: parent.width
          foreground: root.contentForeground
          strength: 0.12
        }

        Text {
          visible: root.dossier && root.dossier.counts
          text: {
            var c = root.dossier.counts || {}
            return "today · " + (c.tools || 0) + " tools · " + (c.deny || 0) + " denied · " + (c.allow || 0) + " allowed"
          }
          color: root.contentForeground
          opacity: 0.45
          font.family: root.contentFontFamily
          font.pixelSize: Style.font.caption
          width: parent.width
        }

        Text {
          visible: root.dossier && root.dossier.lastDenied && root.dossier.lastDenied.summary
          text: "last denied · " + String(root.dossier.lastDenied.summary || "")
          color: root.contentForeground
          opacity: 0.45
          font.family: root.contentFontFamily
          font.pixelSize: Style.font.caption
          elide: Text.ElideMiddle
          width: parent.width
        }

        Text {
          visible: root.sessions.length === 0
          text: "No coding-agent processes. Launch Grok, Claude Code, OpenCode, Codex, or Cursor and they show up here."
          color: root.contentForeground
          opacity: 0.5
          font.family: root.contentFontFamily
          font.pixelSize: Style.font.bodySmall
          wrapMode: Text.Wrap
          width: parent.width
        }

        Repeater {
          model: root.sessions

          Rectangle {
            required property var modelData
            required property int index
            width: panelColumn.width
            implicitHeight: rowCol.implicitHeight + Style.space(12)
            radius: Style.space(6)
            color: index === root.selectedIndex
              ? Qt.rgba(root.contentForeground.r, root.contentForeground.g, root.contentForeground.b, 0.10)
              : Qt.rgba(root.contentForeground.r, root.contentForeground.g, root.contentForeground.b, 0.04)
            border.color: index === root.selectedIndex
              ? Qt.rgba(root.contentForeground.r, root.contentForeground.g, root.contentForeground.b, 0.22)
              : Qt.rgba(root.contentForeground.r, root.contentForeground.g, root.contentForeground.b, 0.06)
            border.width: 1

            MouseArea {
              anchors.fill: parent
              onClicked: root.selectedIndex = index
              onDoubleClicked: root.openCwd()
            }

            Column {
              id: rowCol
              anchors.left: parent.left
              anchors.right: parent.right
              anchors.leftMargin: Style.space(10)
              anchors.rightMargin: Style.space(10)
              anchors.top: parent.top
              anchors.topMargin: Style.space(6)
              spacing: Style.space(2)

              Row {
                width: parent.width
                spacing: Style.space(8)
                Text {
                  text: String(modelData.displayName || modelData.agent)
                  color: root.contentForeground
                  font.family: root.contentFontFamily
                  font.pixelSize: Style.font.bodySmall
                  font.bold: true
                }
                Text {
                  text: "pid " + modelData.pid
                  color: root.contentForeground
                  opacity: 0.55
                  font.family: root.contentFontFamily
                  font.pixelSize: Style.font.caption
                  anchors.verticalCenter: parent.verticalCenter
                }
                Text {
                  text: String(modelData.status || "")
                  color: String(modelData.status) === "waiting" ? Color.accent : root.contentForeground
                  opacity: 0.7
                  font.family: root.contentFontFamily
                  font.pixelSize: Style.font.caption
                  anchors.verticalCenter: parent.verticalCenter
                }
              }

              Text {
                text: {
                  var project = String(modelData.project || "")
                  var cwd = String(modelData.cwd || "")
                  var model = String(modelData.model || "")
                  var envelope = String(modelData.envelope || "seatbelt")
                  var bits = []
                  if (project) bits.push(project)
                  if (envelope && envelope !== "seatbelt") bits.push(envelope)
                  else if (envelope) bits.push(envelope)
                  if (model) bits.push(model)
                  if (cwd && project !== cwd) bits.push(cwd)
                  bits.push(root.rssLabel(modelData.rssBytes))
                  return bits.join(" · ")
                }
                color: root.contentForeground
                opacity: 0.55
                font.family: root.contentFontFamily
                font.pixelSize: Style.font.caption
                elide: Text.ElideMiddle
                width: parent.width
              }
            }
          }
        }

        Item { width: parent.width; height: Style.space(4) }

        Row {
          width: parent.width
          spacing: Style.space(12)

          Text {
            text: "j/k move"
            color: root.contentForeground
            opacity: 0.4
            font.family: root.contentFontFamily
            font.pixelSize: Style.font.caption
          }
          Text {
            text: "x kill"
            color: root.contentForeground
            opacity: 0.4
            font.family: root.contentFontFamily
            font.pixelSize: Style.font.caption
          }
          Text {
            text: "a kill all"
            color: root.contentForeground
            opacity: 0.4
            font.family: root.contentFontFamily
            font.pixelSize: Style.font.caption
          }
          Text {
            text: "o open cwd"
            color: root.contentForeground
            opacity: 0.4
            font.family: root.contentFontFamily
            font.pixelSize: Style.font.caption
          }
          Text {
            text: "r refresh"
            color: root.contentForeground
            opacity: 0.4
            font.family: root.contentFontFamily
            font.pixelSize: Style.font.caption
          }
          Text {
            text: "f freeze"
            color: root.contentForeground
            opacity: 0.4
            font.family: root.contentFontFamily
            font.pixelSize: Style.font.caption
          }
          Text {
            text: "p panic"
            color: root.contentForeground
            opacity: 0.4
            font.family: root.contentFontFamily
            font.pixelSize: Style.font.caption
          }
          Text {
            text: "t alerts"
            color: root.contentForeground
            opacity: 0.4
            font.family: root.contentFontFamily
            font.pixelSize: Style.font.caption
          }
          Text {
            text: "h trust 1h"
            color: root.contentForeground
            opacity: 0.4
            font.family: root.contentFontFamily
            font.pixelSize: Style.font.caption
          }
          Text {
            text: "m mode"
            color: root.contentForeground
            opacity: 0.4
            font.family: root.contentFontFamily
            font.pixelSize: Style.font.caption
          }
          Text {
            text: "i arm hooks"
            color: root.contentForeground
            opacity: 0.4
            font.family: root.contentFontFamily
            font.pixelSize: Style.font.caption
          }
          Text {
            text: "e envelope"
            color: root.contentForeground
            opacity: 0.4
            font.family: root.contentFontFamily
            font.pixelSize: Style.font.caption
          }
          Text {
            text: "w rewind"
            color: root.contentForeground
            opacity: 0.4
            font.family: root.contentFontFamily
            font.pixelSize: Style.font.caption
          }
          Text {
            text: "l lid"
            color: root.contentForeground
            opacity: 0.4
            font.family: root.contentFontFamily
            font.pixelSize: Style.font.caption
          }
        }
      }
    }
  }
}
