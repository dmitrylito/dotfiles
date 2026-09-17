import Quickshell
import Quickshell.Wayland
import QtQuick
import qs.Commons
import qs.Ui

// Full-screen alert for a starting meeting. Summoned by the `meeting-alert`
// CLI: omarchy-shell shell summon dmitrylito.meeting-alert '<payload json>'
// Payload: {title, time, calendar, link, autoDismissSeconds, snoozeMinutes}
Item {
  id: root

  property string omarchyPath: Quickshell.env("OMARCHY_PATH")
  property var shell: null
  property var manifest: null

  property bool opened: false
  property string title: ""
  property string timeText: ""
  property string calendar: ""
  property string link: ""
  property int autoDismissSeconds: 120
  property int snoozeMinutes: 5

  property color background: Color.menu.background
  property color foreground: Color.menu.text
  property color border: Color.menu.border
  property var borderSpec: Border.surfaceSpec("menu", "border", border, Math.max(1, Style.space(2)))
  property color scrim: Color.menu.scrim

  function open(payloadJson) {
    var payload = ({})
    try { payload = JSON.parse(payloadJson || "{}") } catch (e) { payload = ({}) }

    root.title = String(payload.title || "Meeting")
    root.timeText = String(payload.time || "")
    root.calendar = String(payload.calendar || "")
    root.link = String(payload.link || "")
    if (payload.autoDismissSeconds !== undefined) root.autoDismissSeconds = Number(payload.autoDismissSeconds)
    if (payload.snoozeMinutes !== undefined) root.snoozeMinutes = Number(payload.snoozeMinutes)

    root.opened = true
    autoDismiss.restart()
    Qt.callLater(function() { keyCatcher.forceActiveFocus() })
  }

  function close() {
    root.opened = false
    autoDismiss.stop()
  }

  function dismiss() {
    root.close()
    if (root.shell && typeof root.shell.hide === "function")
      root.shell.hide((root.manifest && root.manifest.id) || "dmitrylito.meeting-alert")
  }

  function join() {
    if (root.link) Quickshell.execDetached(["xdg-open", root.link])
    root.dismiss()
  }

  function snooze() {
    Quickshell.execDetached([root.omarchyPath + "/bin/omarchy-reminder", String(root.snoozeMinutes), root.title])
    root.dismiss()
  }

  Timer {
    id: autoDismiss
    interval: Math.max(5, root.autoDismissSeconds) * 1000
    onTriggered: root.dismiss()
  }

  PanelWindow {
    id: panel
    visible: root.opened
    anchors { top: true; bottom: true; left: true; right: true }
    color: "transparent"
    WlrLayershell.namespace: "dmitrylito-meeting-alert"
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.Exclusive
    exclusionMode: ExclusionMode.Ignore

    Rectangle {
      anchors.fill: parent
      color: root.scrim
      opacity: 0.96
    }

    MouseArea {
      anchors.fill: parent
      onClicked: root.dismiss()
    }

    BorderSurface {
      id: card
      width: Math.min(Style.space(760), panel.width - Style.gapsOut * 2)
      height: Math.min(content.implicitHeight + Style.spacing.panelPadding * 2, panel.height - Style.gapsOut * 2)
      radius: Style.cornerRadius
      anchors.centerIn: parent
      color: root.background
      borderSpec: root.borderSpec
      padding: Style.spacing.panelPadding

      MouseArea { anchors.fill: parent; onClicked: {} }

      Item {
        id: keyCatcher
        anchors.fill: parent
        focus: true
        Keys.priority: Keys.BeforeItem
        Keys.onPressed: function(event) {
          if (event.key === Qt.Key_Escape) {
            root.dismiss()
            event.accepted = true
          } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
            if (root.link) root.join()
            else root.dismiss()
            event.accepted = true
          } else if (event.key === Qt.Key_S) {
            root.snooze()
            event.accepted = true
          } else if (event.key === Qt.Key_J) {
            root.join()
            event.accepted = true
          }
        }
      }

      Column {
        id: content
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        anchors.leftMargin: card.contentLeftInset
        anchors.rightMargin: card.contentRightInset
        spacing: Style.space(14)

        Text {
          textFormat: Text.PlainText
          width: parent.width
          text: root.timeText ? (root.timeText + (root.calendar ? "  ·  " + root.calendar : "")) : root.calendar
          color: root.foreground
          opacity: 0.65
          font.family: Style.font.menuFamily
          font.pixelSize: Style.font.heading
          elide: Text.ElideRight
        }

        Text {
          textFormat: Text.PlainText
          width: parent.width
          text: root.title
          color: root.foreground
          font.family: Style.font.menuFamily
          font.pixelSize: Style.font.title * 2
          font.bold: true
          wrapMode: Text.WordWrap
          maximumLineCount: 3
          elide: Text.ElideRight
        }

        Row {
          spacing: Style.space(12)

          Repeater {
            model: [
              { key: "join", label: "Join  ⏎", shown: root.link !== "" },
              { key: "snooze", label: "Snooze " + root.snoozeMinutes + "m  S", shown: true },
              { key: "dismiss", label: "Dismiss  Esc", shown: true }
            ]

            Rectangle {
              visible: modelData.shown
              radius: Style.cornerRadius
              color: buttonArea.containsMouse ? root.foreground : "transparent"
              border.color: root.foreground
              border.width: 1
              opacity: buttonArea.containsMouse ? 1 : 0.8
              width: buttonLabel.implicitWidth + Style.space(28)
              height: buttonLabel.implicitHeight + Style.space(16)

              Text {
                id: buttonLabel
                anchors.centerIn: parent
                textFormat: Text.PlainText
                text: modelData.label
                color: buttonArea.containsMouse ? root.background : root.foreground
                font.family: Style.font.menuFamily
                font.pixelSize: Style.font.heading
              }

              MouseArea {
                id: buttonArea
                anchors.fill: parent
                hoverEnabled: true
                onClicked: {
                  if (modelData.key === "join") root.join()
                  else if (modelData.key === "snooze") root.snooze()
                  else root.dismiss()
                }
              }
            }
          }
        }
      }
    }
  }
}
