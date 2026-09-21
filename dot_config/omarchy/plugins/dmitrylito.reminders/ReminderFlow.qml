// Clone of omarchy.reminders (the SUPER+CTRL+R flow), with two changes:
//
//  - the prompt draws a blinking caret. The stock flow renders the typed text
//    in a plain Text with a hand-rolled key handler, so there was never a caret
//    to see and an empty prompt looked unfocused.
//  - the first step takes a duration (45m, 2h30) or a clock time (14:30, 9am),
//    not only a bare count of minutes, and echoes back when it will fire.
//
// omarchy-reminder still only accepts minutes, so the clock time is resolved
// against the current time in ReminderFlowModel.parseWhen before being passed.

import Quickshell
import Quickshell.Wayland
import QtQuick
import qs.Commons
import qs.Ui
import "ReminderFlowModel.js" as ReminderFlowModel

Item {
  id: root

  property string omarchyPath: Quickshell.env("OMARCHY_PATH")
  property var shell: null
  property var manifest: null

  property bool opened: false
  property string step: "minutes"
  property string minutes: ""
  property string filterText: ""
  property string fontFamily: Style.font.menuFamily

  property color background: Color.menu.background
  property color foreground: Color.menu.text
  property color border: Color.menu.border
  property var borderSpec: Border.surfaceSpec("menu", "border", border, Math.max(1, Style.space(2)))
  property color scrim: Color.menu.scrim
  readonly property int cornerRadius: Style.cornerRadius
  property int contentMargin: Style.spacing.panelPadding
  property int headerHeight: Math.max(Style.space(34), Style.font.title + Style.spacing.controlPaddingY * 2)
  property int hintHeight: Math.round(Style.font.caption * 1.7)
  property int cardWidth: Math.min(Style.space(340), panel.width - Style.gapsOut * 2)
  property int cardHeight: Math.min(contentMargin * 2 + headerHeight + hintHeight, panel.height - Style.gapsOut * 2)
  readonly property string promptText: root.step === "message" ? "Reminder message" : "Remind me when"

  // Drives the hint's countdown, so "in 45m" stays honest while the prompt sits
  // open. Only ticks while it is on screen.
  property double nowMs: Date.now()
  property bool caretOn: true

  readonly property string hintText: root.step === "message"
    ? "Enter to set · Esc to cancel"
    : ReminderFlowModel.whenHint(root.filterText, root.nowMs)

  function open(payloadJson) {
    var payload = ({})
    try { payload = JSON.parse(payloadJson || "{}") } catch (e) { payload = ({}) }
    if (payload.fontFamily) root.fontFamily = payload.fontFamily

    root.opened = true
    root.step = "minutes"
    root.minutes = ""
    root.filterText = ""
    root.nowMs = Date.now()
    root.caretOn = true

    Qt.callLater(function() { keyCatcher.forceActiveFocus() })
  }

  function close() {
    root.opened = false
  }

  function dismiss() {
    root.opened = false
    if (root.shell && typeof root.shell.hide === "function")
      root.shell.hide((root.manifest && root.manifest.id) || "omarchy.reminders")
  }

  function toggle() {
    if (root.opened) root.dismiss()
    else root.open("{}")
  }

  function setFilter(nextFilter) {
    root.filterText = nextFilter
    // Solid caret while typing; the blink only resumes once the keys stop.
    root.caretOn = true
    caretTimer.restart()
  }

  function submit() {
    var selection = root.filterText

    if (root.step === "minutes") {
      if (!selection.trim()) {
        root.dismiss()
        return
      }

      var nextMinutes = ReminderFlowModel.parseWhen(selection, Date.now())

      if (!nextMinutes) {
        Quickshell.execDetached([root.omarchyPath + "/bin/omarchy-notification-send", "Invalid reminder", "Try 45m, 2h30, 14:30 or 9am"])
        return
      }

      root.minutes = String(nextMinutes)
      root.step = "message"
      root.filterText = ""
      Qt.callLater(function() { keyCatcher.forceActiveFocus() })
      return
    }

    if (root.step === "message") {
      var args = [root.omarchyPath + "/bin/omarchy-reminder"].concat(ReminderFlowModel.reminderArgs(root.minutes, selection))
      root.dismiss()
      Quickshell.execDetached(args)
    }
  }

  Timer {
    id: caretTimer
    interval: 530
    repeat: true
    running: root.opened
    onTriggered: root.caretOn = !root.caretOn
  }

  Timer {
    interval: 1000
    repeat: true
    running: root.opened && root.step === "minutes"
    onTriggered: root.nowMs = Date.now()
  }

  PanelWindow {
    id: panel
    visible: root.opened
    anchors { top: true; bottom: true; left: true; right: true }
    color: "transparent"
    WlrLayershell.namespace: "omarchy-reminders"
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.Exclusive
    exclusionMode: ExclusionMode.Ignore

    Rectangle {
      anchors.fill: parent
      color: root.scrim
    }

    MouseArea {
      anchors.fill: parent
      onClicked: root.dismiss()
    }

    BorderSurface {
      id: card
      width: root.cardWidth
      height: root.cardHeight
      radius: root.cornerRadius
      anchors.centerIn: parent
      color: root.background
      borderSpec: root.borderSpec
      padding: root.contentMargin

      MouseArea { anchors.fill: parent; onClicked: {} }

      Item {
        id: keyCatcher
        anchors.fill: parent
        focus: true

        Keys.priority: Keys.BeforeItem
        Keys.onPressed: function(event) {
          if (event.key === Qt.Key_Escape) {
            if (root.filterText) root.setFilter("")
            else root.dismiss()
            event.accepted = true
          } else if (Util.editsFilter(event, root.filterText)) {
            root.setFilter(Util.editedFilter(event, root.filterText))
            event.accepted = true
          } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
            root.submit()
            event.accepted = true
          } else if (event.text && event.text.length === 1 && event.text.charCodeAt(0) >= 32 && event.text.charCodeAt(0) !== 127) {
            root.setFilter(root.filterText + event.text)
            event.accepted = true
          }
        }
      }

      Item {
        anchors.fill: parent
        anchors.topMargin: card.contentTopInset
        anchors.rightMargin: card.contentRightInset
        anchors.bottomMargin: card.contentBottomInset
        anchors.leftMargin: card.contentLeftInset

        Column {
          anchors.left: parent.left
          anchors.right: parent.right
          anchors.verticalCenter: parent.verticalCenter
          spacing: Style.space(2)

          Row {
            id: inputLine
            width: parent.width
            spacing: Style.space(2)

            Text {
              id: valueText
              textFormat: Text.PlainText
              visible: root.filterText.length > 0
              text: root.filterText
              // Elide from the left so the caret end of a long entry stays put.
              width: Math.min(implicitWidth, inputLine.width - caret.width - inputLine.spacing)
              elide: Text.ElideLeft
              color: root.foreground
              font.family: root.fontFamily
              font.pixelSize: Style.font.heading
              anchors.verticalCenter: parent.verticalCenter
            }

            Rectangle {
              id: caret
              width: Math.max(1, Style.space(2))
              height: Math.round(Style.font.heading * 1.15)
              color: root.foreground
              opacity: root.caretOn ? 1 : 0
              anchors.verticalCenter: parent.verticalCenter
            }

            Text {
              textFormat: Text.PlainText
              visible: root.filterText.length === 0
              text: root.promptText + "..."
              width: Math.min(implicitWidth, inputLine.width - caret.width - inputLine.spacing * 2)
              elide: Text.ElideRight
              color: root.foreground
              opacity: 0.58
              font.family: root.fontFamily
              font.pixelSize: Style.font.heading
              anchors.verticalCenter: parent.verticalCenter
            }
          }

          Text {
            textFormat: Text.PlainText
            width: parent.width
            text: root.hintText
            color: root.foreground
            opacity: 0.5
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
            elide: Text.ElideRight
          }
        }
      }
    }
  }
}
