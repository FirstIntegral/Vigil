import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import qs.Commons
import qs.Ui

// Same chrome as omarchy.polkit: scrim, BorderSurface, [polkit] tokens.
// Ghosts are Hyprland window outlines for the pending call.
Item {
  id: root

  property var shell: null
  property var manifest: null
  property bool opened: false
  property var request: null

  readonly property var service: shell && shell.serviceFor ? shell.serviceFor("xyz.brwsk.vigil") : null
  readonly property var pending: service && service.pending ? service.pending : []
  readonly property var current: {
    if (root.request) return root.request
    if (pending && pending.length) return pending[0]
    return null
  }
  readonly property string kind: root.current ? String(root.current.kind || "tool") : "tool"
  readonly property var ghosts: root.current && root.current.ghosts ? root.current.ghosts : []
  readonly property bool awayCard: kind === "away" || kind === "surprise"

  property color accent: Color.polkit.accent
  property color background: Color.polkit.background
  property color foreground: Color.polkit.text
  property color border: Color.polkit.border
  property var borderSpec: Border.surfaceSpec("polkit", "border", border, Math.max(1, Style.space(2)), "border-alpha")
  property color scrim: Color.polkit.scrim
  readonly property int cornerRadius: Style.cornerRadius
  property int contentMargin: Style.spacing.panelPadding
  property string fontFamily: Style.font.menuFamily

  function open(payloadJson) {
    try { root.request = payloadJson ? JSON.parse(payloadJson) : null }
    catch (e) { root.request = null }
    root.opened = true
  }

  function close() {
    root.opened = false
    root.request = null
  }

  function helperPath() {
    return decodeURIComponent(Qt.resolvedUrl("bin/vigil").toString().replace(/^file:\/\//, ""))
  }

  function decide(action) {
    var row = root.current
    if (!row || !row.id) { root.close(); return }
    if (root.service && typeof root.service.decide === "function")
      root.service.decide(row.id, action)
    else
      decideProc.command = [helperPath(), "decide", String(row.id), action]
    decideProc.running = true
  }

  onPendingChanged: {
    if (pending && pending.length > 0) root.opened = true
    else if (!root.request) root.opened = false
  }

  IpcHandler {
    target: "xyz.brwsk.vigil.overlay"
    function open(payloadJson: string): string { root.open(payloadJson); return "ok" }
    function close(): string { root.close(); return "ok" }
  }

  Process {
    id: decideProc
    running: false
    command: []
    onExited: {
      root.request = null
      if (!root.pending || root.pending.length === 0) root.close()
    }
  }

  PanelWindow {
    id: panel
    visible: root.opened && root.current !== null
    anchors { top: true; bottom: true; left: true; right: true }
    color: "transparent"
    WlrLayershell.namespace: "omarchy-vigil"
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.Exclusive
    exclusionMode: ExclusionMode.Ignore

    Rectangle {
      anchors.fill: parent
      color: root.ghosts.length > 0
        ? Qt.rgba(root.scrim.r, root.scrim.g, root.scrim.b, 0.42)
        : root.scrim
    }

    Repeater {
      model: root.ghosts
      Rectangle {
        required property var modelData
        x: (modelData.at && modelData.at.length) ? Number(modelData.at[0]) : 0
        y: (modelData.at && modelData.at.length > 1) ? Number(modelData.at[1]) : 0
        width: (modelData.size && modelData.size.length) ? Number(modelData.size[0]) : 0
        height: (modelData.size && modelData.size.length > 1) ? Number(modelData.size[1]) : 0
        color: "transparent"
        radius: root.cornerRadius
        border.width: Math.max(2, Style.space(2))
        border.color: Color.urgent
      }
    }

    MouseArea {
      anchors.fill: parent
      onClicked: keyCatcher.forceActiveFocus()
    }

    Rectangle {
      width: Math.min(justificationText.implicitWidth + Style.space(24), panel.width - Style.gapsOut * 2)
      height: Style.space(28)
      anchors.horizontalCenter: card.horizontalCenter
      anchors.bottom: card.top
      anchors.bottomMargin: Style.space(10)
      radius: root.cornerRadius
      color: root.background

      Text {
        id: justificationText
        textFormat: Text.PlainText
        anchors.fill: parent
        anchors.leftMargin: Style.space(12)
        anchors.rightMargin: Style.space(12)
        text: root.current ? String(root.current.title || "Authentication is needed") : ""
        color: root.foreground
        font.family: root.fontFamily
        font.pixelSize: Style.font.bodySmall
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideMiddle
      }
    }

    BorderSurface {
      id: card
      width: Math.min(Style.space(420), Math.max(Style.space(280), panel.width - Style.gapsOut * 2))
      height: Math.min(innerCol.implicitHeight + contentMargin * 2, panel.height - Style.gapsOut * 4)
      radius: root.cornerRadius
      anchors.centerIn: parent
      color: root.background
      borderSpec: root.borderSpec
      padding: root.contentMargin

      Item {
        id: keyCatcher
        anchors.fill: parent
        focus: true
        Keys.priority: Keys.BeforeItem
        Keys.onPressed: function(event) {
          if (root.awayCard) {
            if (event.key === Qt.Key_Escape || event.key === Qt.Key_N) {
              root.decide("deny"); event.accepted = true
            } else if (event.key === Qt.Key_Y || event.key === Qt.Key_Return || event.key === Qt.Key_Enter || event.key === Qt.Key_U) {
              root.decide("unfreeze"); event.accepted = true
            } else if (event.key === Qt.Key_W) {
              root.decide("rewind"); event.accepted = true
            }
            return
          }
          if (event.key === Qt.Key_Escape || event.key === Qt.Key_N) {
            root.decide("deny"); event.accepted = true
          } else if (event.key === Qt.Key_Y || event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
            root.decide("allow"); event.accepted = true
          } else if (event.key === Qt.Key_S) {
            root.decide("session"); event.accepted = true
          } else if (event.key === Qt.Key_A) {
            root.decide("always"); event.accepted = true
          } else if (event.key === Qt.Key_D) {
            root.decide("deny-always"); event.accepted = true
          } else if (event.key === Qt.Key_W) {
            root.decide("rewind"); event.accepted = true
          }
        }
      }

      Column {
        id: innerCol
        anchors.fill: parent
        anchors.topMargin: card.contentTopInset
        anchors.rightMargin: card.contentRightInset
        anchors.bottomMargin: card.contentBottomInset
        anchors.leftMargin: card.contentLeftInset
        spacing: Style.space(10)

        Text {
          text: "\uf023"
          color: root.accent
          font.family: root.fontFamily
          font.pixelSize: Style.font.iconLarge
        }

        Text {
          textFormat: Text.PlainText
          text: root.current ? String(root.current.reason || "") : ""
          color: root.foreground
          opacity: 0.7
          font.family: root.fontFamily
          font.pixelSize: Style.font.bodySmall
          wrapMode: Text.Wrap
          width: parent.width
        }

        Text {
          visible: root.current && root.current.article
          textFormat: Text.PlainText
          text: root.current ? String(root.current.article || "") : ""
          color: root.accent
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
          wrapMode: Text.Wrap
          width: parent.width
        }

        Text {
          textFormat: Text.PlainText
          text: root.current ? String(root.current.summary || "") : ""
          color: root.foreground
          font.family: root.fontFamily
          font.pixelSize: Style.font.bodySmall
          wrapMode: Text.Wrap
          width: parent.width
        }

        Text {
          visible: root.current && root.current.blast
          textFormat: Text.PlainText
          text: root.current ? String(root.current.blast || "") : ""
          color: root.foreground
          opacity: 0.55
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
          wrapMode: Text.Wrap
          width: parent.width
        }

        Text {
          textFormat: Text.PlainText
          text: {
            if (!root.current) return ""
            var agent = String(root.current.agent || "agent")
            var env = String(root.current.envelope || "")
            var cwd = String(root.current.cwd || "")
            var bits = [agent]
            if (env) bits.push(env)
            if (cwd) bits.push(cwd)
            return bits.join(" · ")
          }
          color: root.foreground
          opacity: 0.36
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
          elide: Text.ElideMiddle
          width: parent.width
        }

        Text {
          text: root.awayCard
            ? "N stay frozen   U unfreeze   W rewind"
            : "N deny   Y once   S session   A ticket"
          color: root.foreground
          opacity: 0.36
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
          width: parent.width
        }
      }
    }
  }
}
