// Bell bar widget: recent-notification list, reminder management, and a DND
// toggle for the Omarchy 4 notifications service. Notification history lives on
// disk (one JSON file per entry under the service's historyDir); live toasts
// come from service.popupModel; reminders come from `omarchy reminder`, which
// backs each one with a transient systemd user timer.
// Left-click (or `omarchy-shell notification-center toggle`) opens the popup,
// right-click toggles Do Not Disturb.
//
// The popup has two tabs. Notifications is always the one that opens — the tab
// resets on every open so the bell stays a one-click read of what just came in,
// and reminders are a deliberate second click.
//
// It is a KeyboardPanel rather than the PopupCard the rest of this widget grew
// up on. A PopupCard is an xdg-popup under a layer surface that never takes
// keyboard focus, so its text fields only received keys once the pointer left
// the card and Hyprland's focus grab re-picked a surface to enter. KeyboardPanel
// primes WlrKeyboardFocus.Exclusive at map time, which is what the first-party
// panels with inline editors (wifi passphrase, weather) already use.

import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui
import "NotificationLogic.js" as NotificationLogic

BarWidget {
  id: root
  moduleName: "omacom.notification-center"

  property bool popupOpen: false
  function close() { popupOpen = false }
  function toggle() { popupOpen = !popupOpen }

  property string activeTab: "notifications"

  onPopupOpenChanged: {
    if (!popupOpen) {
      editingUnit = ""
      return
    }
    activeTab = "notifications"
    refreshHistory()
    refreshReminders()
  }

  // Landing on Reminders should be typeable straight away. callLater so the
  // field exists and the layout has settled before focus moves to it.
  onActiveTabChanged: if (activeTab === "reminders") Qt.callLater(function() {
    if (root.popupOpen && root.activeTab === "reminders") composeWhen.forceActiveFocus()
  })

  // omarchy hands the omarchy.notifications proxy only to plugins declaring
  // kind "bar" (shell.qml createScopedPluginShell), so a bar-widget has to read
  // the service's on-disk state instead of its QML object.
  readonly property string stateDir: Quickshell.env("HOME") + "/.local/state/omarchy/"
  readonly property string popupDir: stateDir + "notifications/"
  readonly property string historyDir: popupDir + "history/"
  readonly property string imagesDir: popupDir + "images/"
  readonly property string settingsPath: stateDir + "notifications.json"

  property int liveCount: 0
  property bool dnd: false

  function toggleDnd() {
    if (dndProc.running) return
    dnd = !dnd
    dndProc.running = true
  }

  function loadState(raw) {
    var lines = String(raw || "").split("\n")
    var count = Number(lines[0] || 0)
    var changed = count !== liveCount
    liveCount = count
    dnd = String(lines[1] || "") === "dnd"
    if (changed && popupOpen) refreshTimer.restart()
  }

  function sanitizeBody(s, app, appIcon) {
    return NotificationLogic.sanitizeBody(s, app, appIcon)
  }

  function notificationIconSource(icon) {
    var value = String(icon || "")
    if (value.length === 0) return ""
    if (value.indexOf("file://") === 0 || value.indexOf("image://") === 0) return value
    if (value.charAt(0) === "/") return Util.fileUrl(value)
    return Quickshell.iconPath(value, true)
  }

  readonly property string icon: {
    if (dnd) return "󰂛"
    if (liveCount > 0) return "󱅫"
    return "󰂚"
  }

  // Theme palette (mirrors the notification cards so the popup matches the
  // rest of the notification stack).
  readonly property color colForeground: Color.foreground
  readonly property color colDim: Qt.darker(Color.foreground, 1.4)
  readonly property color colBorder: Style.normalBorderFor(Color.foreground, Color.accent)
  readonly property color colSurface: Style.normalFillFor(Color.foreground, Color.accent)
  readonly property color colAccent: Color.accent
  readonly property int cardRadius: Style.cornerRadius

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  ListModel { id: historyModel }

  function refreshHistory() {
    if (!historyDir || historyProc.running) return
    historyProc.running = true
  }

  function loadHistory(raw) {
    var rows = NotificationLogic.parseHistoryFiles(raw)
    historyModel.clear()
    for (var i = 0; i < rows.length; i++) historyModel.append(rows[i])
  }

  property var removeQueue: []

  function dismissHistoryRow(index) {
    if (index < 0 || index >= historyModel.count) return
    var stem = String(historyModel.get(index).fileName).replace(/\.json$/, "")
    historyModel.remove(index)
    removeQueue.push(stem)
    runNextRemove()
  }

  function runNextRemove() {
    if (removeProc.running || removeQueue.length === 0) return
    var stem = removeQueue.shift()
    removeProc.command = ["bash", "-c",
      "rm -f \"$1/$2.json\" \"$3/$2\"-*", "--",
      root.historyDir, stem, root.imagesDir]
    removeProc.running = true
  }

  // History rows are dead notifications — the sender is long gone and no
  // D-Bus action survives — so clicking one focuses the sending window, which
  // is what clicking a chat toast is for.
  function focusHistoryRow(index) {
    if (index < 0 || index >= historyModel.count) return
    var row = historyModel.get(index)
    var pattern = NotificationLogic.focusPattern(row.app, row.appIcon, row.body)
    if (!pattern) return
    focusProc.command = ["omarchy-hyprland-focus-app", pattern]
    focusProc.running = true
    root.popupOpen = false
  }

  function clearAll() {
    if (!clearProc.running) clearProc.running = true
    historyModel.clear()
  }

  // ---------------------------------------------------------------- reminders
  //
  // `omarchy reminder` owns the model: each reminder is a transient systemd
  // user timer (omarchy-reminder-<minutes>m-<epoch>.timer) plus an optional
  // message file under $XDG_RUNTIME_DIR/omarchy-reminders. There is no API to
  // move a timer's fire time, so rescheduling is stop-then-recreate — the unit
  // name changes, which is why rows are keyed by unit and edit state is dropped
  // whenever the list reloads.

  ListModel { id: remindersModel }

  // Unit of the row currently being rescheduled, "" when none.
  property string editingUnit: ""
  property string editWhen: ""

  // Countdown clock for the reminder rows. Only ticks while they are on screen.
  property double nowMs: Date.now()

  property var reminderQueue: []

  function refreshReminders() {
    if (remindersProc.running) return
    remindersProc.running = true
  }

  function loadReminders(raw) {
    var rows = NotificationLogic.parseReminders(raw)
    remindersModel.clear()
    for (var i = 0; i < rows.length; i++) remindersModel.append(rows[i])
    nowMs = Date.now()
    if (editingUnit.length > 0 && !hasReminder(editingUnit)) editingUnit = ""
  }

  function hasReminder(unit) {
    for (var i = 0; i < remindersModel.count; i++)
      if (remindersModel.get(i).unit === unit) return true
    return false
  }

  function queueReminderAction(command) {
    reminderQueue.push(command)
    runNextReminderAction()
  }

  function runNextReminderAction() {
    if (reminderProc.running || reminderQueue.length === 0) return
    reminderProc.command = reminderQueue.shift()
    reminderProc.running = true
  }

  // Mirrors omarchy-reminder's own clear path: stop both units the transient
  // timer created, drop the message file, then nudge the bar indicator, which
  // has no other way to learn the timer went away.
  function cancelReminder(unit) {
    if (!unit) return
    queueReminderAction(["bash", "-c",
      "dir=\"${XDG_RUNTIME_DIR:-/tmp}/omarchy-reminders\"\n" +
      "systemctl --user stop \"$1.timer\" \"$1.service\" >/dev/null 2>&1 || true\n" +
      "rm -f \"$dir/$1.message\"\n" +
      "omarchy-shell -q omarchy.indicators refresh >/dev/null 2>&1 || true",
      "--", unit])
  }

  function createReminder(minutes, message) {
    var valid = NotificationLogic.validMinutes(minutes)
    if (valid === 0) return false
    var text = String(message || "").trim()
    queueReminderAction(text.length > 0
      ? ["omarchy-reminder", String(valid), text]
      : ["omarchy-reminder", String(valid)])
    return true
  }

  function rescheduleReminder(unit, minutes, message) {
    var valid = NotificationLogic.validMinutes(minutes)
    if (valid === 0) return false
    cancelReminder(unit)
    return createReminder(valid, message)
  }

  // Seeded with the clock time the reminder currently fires at, since that is
  // the fact being changed; a duration ("20m") is still accepted in its place.
  function beginEdit(unit, at) {
    editWhen = NotificationLogic.clockString(at)
    editingUnit = unit
  }

  // No signal from the service reaches a bar-widget, so poll the two pieces of
  // its state we need: one file per on-screen toast, and the DND setting.
  Timer {
    interval: 3000
    running: true
    repeat: true
    triggeredOnStart: true
    onTriggered: if (!stateProc.running) stateProc.running = true
  }

  Process {
    id: stateProc
    running: false
    command: ["bash", "-c",
      "shopt -s nullglob\n" +
      "settings=$2\n" +
      "set -- \"$1\"/*.json\n" +
      "printf '%s\\n' \"$#\"\n" +
      "grep -qs '\"dnd\"[[:space:]]*:[[:space:]]*true' \"$settings\" && echo dnd || echo ok",
      "--", root.popupDir, root.settingsPath]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: root.loadState(text)
    }
  }

  Process {
    id: dndProc
    running: false
    command: ["omarchy-shell", "-q", "notifications", "toggleDnd"]
    onExited: if (!stateProc.running) stateProc.running = true
  }

  Process {
    id: clearProc
    running: false
    command: ["omarchy-shell", "-q", "notifications", "clear"]
  }

  Timer {
    id: refreshTimer
    interval: 500
    onTriggered: root.refreshHistory()
  }

  Process {
    id: historyProc
    running: false
    command: ["bash", "-c",
      "cd \"$1\" 2>/dev/null || exit 0\n" +
      "for f in *.json; do [[ -e $f ]] || exit 0; printf '%s\\t' \"$f\"; cat \"$f\"; done",
      "--", root.historyDir]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: root.loadHistory(text)
    }
  }

  Process {
    id: focusProc
    running: false
  }

  Process {
    id: removeProc
    running: false
    onExited: root.runNextRemove()
  }

  Process {
    id: remindersProc
    running: false
    command: ["omarchy-reminder", "show", "--json"]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: root.loadReminders(text)
    }
  }

  // Reminder mutations run one at a time so a reschedule's stop always lands
  // before its recreate. The list is only re-read once the queue drains.
  Process {
    id: reminderProc
    running: false
    onExited: {
      if (root.reminderQueue.length > 0) root.runNextReminderAction()
      else root.refreshReminders()
    }
  }

  Timer {
    interval: 1000
    repeat: true
    running: root.popupOpen && root.activeTab === "reminders"
    onTriggered: {
      root.nowMs = Date.now()
      // Rows are sorted by fire time, so the first one is the only one that can
      // have just fired and left the timer list.
      if (remindersModel.count > 0 && remindersModel.get(0).at * 1000 <= root.nowMs)
        root.refreshReminders()
    }
  }

  Timer {
    interval: 20000
    repeat: true
    running: root.popupOpen && root.activeTab === "reminders"
    onTriggered: root.refreshReminders()
  }

  IpcHandler {
    target: "notification-center"
    function toggle(): string { root.toggle(); return root.popupOpen ? "open" : "closed" }
  }

  WidgetButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: root.icon
    active: root.liveCount > 0 && !root.dnd
    tooltipText: root.dnd ? "Do Not Disturb" : "Notifications"

    onPressed: function(b) {
      if (b === Qt.RightButton) {
        root.toggleDnd()
      } else {
        root.popupOpen = !root.popupOpen
      }
    }
  }

  KeyboardPanel {
    id: popup
    anchorItem: button
    bar: root.bar
    owner: root
    open: root.popupOpen
    focusTarget: keyCatcher
    contentWidth: popup.fittedContentWidth(Style.space(440))
    contentHeight: popup.cappedContentHeight(Style.space(540))

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      // Every key on the Reminders tab belongs to a text field, and the
      // catcher's hjkl / x / space bindings would eat them.
      blocked: root.activeTab === "reminders"
      onCloseRequested: root.close()

      ColumnLayout {
        anchors.fill: parent
        spacing: Style.space(10)

        // ----------------------------------------- tabs + DND
        RowLayout {
          Layout.fillWidth: true
          spacing: Style.space(8)

          ButtonGroup {
            options: [
              { value: "notifications", label: "Notifications" },
              { value: "reminders", label: remindersModel.count > 0
                  ? "Reminders " + remindersModel.count
                  : "Reminders" }
            ]
            value: root.activeTab
            foreground: root.colForeground
            accent: root.colAccent
            fontFamily: root.bar ? root.bar.fontFamily : ""
            fontSize: Style.font.caption
            focusable: false
            onChanged: function(tab) { root.activeTab = tab }
          }

          Item { Layout.fillWidth: true }

          BorderSurface {
            id: dndPill
            visible: root.activeTab === "notifications"
            Layout.preferredHeight: Math.max(Style.space(24), Style.font.bodySmall + Style.spacing.controlPaddingY * 2)
            Layout.preferredWidth: dndLabel.implicitWidth + dndGlyph.implicitWidth + Style.space(18)
            radius: Math.min(Style.space(12), root.cardRadius + Style.space(6))
            color: dndOn ? root.colAccent : root.colSurface
            borderSpec: Border.flat(dndOn ? root.colAccent : root.colBorder, Style.normalBorderWidth)

            readonly property bool dndOn: root.dnd

            Row {
              anchors.centerIn: parent
              spacing: Style.space(4)

              Text {
                id: dndGlyph
                text: dndPill.dndOn ? "󰂛" : "󰂚"
                font.family: root.bar ? root.bar.fontFamily : ""
                color: dndPill.dndOn ? Color.background : root.colDim
                font.pixelSize: Style.font.body
                anchors.verticalCenter: parent.verticalCenter
              }

              Text {
                id: dndLabel
                text: dndPill.dndOn ? "DND on" : "DND off"
                font.family: root.bar ? root.bar.fontFamily : ""
                color: dndPill.dndOn ? Color.background : root.colDim
                font.pixelSize: Style.font.caption
                font.bold: true
                anchors.verticalCenter: parent.verticalCenter
              }
            }

            MouseArea {
              anchors.fill: parent
              hoverEnabled: true
              cursorShape: Qt.PointingHandCursor
              onClicked: root.toggleDnd()
            }
          }
        }

        // ----------------------------------------- action row
        RowLayout {
          Layout.fillWidth: true
          visible: root.activeTab === "notifications" && historyModel.count > 0
          spacing: Style.space(8)

          Text {
            text: historyModel.count === 1 ? "1 recent" : historyModel.count + " recent"
            font.family: root.bar ? root.bar.fontFamily : ""
            color: root.colDim
            font.pixelSize: Style.font.caption
          }

          Item { Layout.fillWidth: true }

          BorderSurface {
            Layout.preferredWidth: actionLabel.implicitWidth + Style.space(16)
            Layout.preferredHeight: Math.max(Style.space(22), Style.font.bodySmall + Style.spacing.controlPaddingY * 2)
            radius: Math.min(Style.space(6), root.cardRadius)
            color: actionArea.containsMouse ? root.colBorder : "transparent"

            Text {
              id: actionLabel
              anchors.centerIn: parent
              text: "Clear"
              font.family: root.bar ? root.bar.fontFamily : ""
              color: root.colForeground
              font.pixelSize: Style.font.caption
            }

            MouseArea {
              id: actionArea
              anchors.fill: parent
              hoverEnabled: true
              cursorShape: Qt.PointingHandCursor
              onClicked: root.clearAll()
            }
          }
        }

        // ----------------------------------------- notification list
        ListView {
          id: listView
          Layout.fillWidth: true
          Layout.fillHeight: true
          clip: true
          spacing: Style.space(8)
          model: historyModel
          visible: root.activeTab === "notifications" && count > 0

          delegate: BorderSurface {
            id: rowCard
            required property int index
            required property string fileName
            required property string app
            required property string appIcon
            required property string summary
            required property string body
            required property string image
            required property string glyph
            required property int urgency
            required property double timestamp

            readonly property bool hasMedia: image.length > 0 && (
              image.indexOf("image://icon//") === 0 || image.indexOf("file://") === 0)
            readonly property string smallIconSource: image.length > 0 ? image : root.notificationIconSource(appIcon)
            readonly property bool hasIcon: !hasMedia && smallIconSource.length > 0
            readonly property string sanitizedBody: root.sanitizeBody(body, app, appIcon)

            width: listView.width
            implicitHeight: rowContent.implicitHeight + Style.spacing.panelGap
            radius: root.cardRadius
            color: "transparent"
            borderSpec: Border.flat(root.colBorder, Style.normalBorderWidth)

            // Declared before rowContent so the row's own close button, a later
            // sibling, keeps the click.
            MouseArea {
              anchors.fill: parent
              cursorShape: Qt.PointingHandCursor
              onClicked: root.focusHistoryRow(rowCard.index)
            }

            RowLayout {
              id: rowContent
              anchors.left: parent.left
              anchors.right: parent.right
              anchors.verticalCenter: parent.verticalCenter
              anchors.leftMargin: rowCard.borderLeft + Style.space(12)
              anchors.rightMargin: rowCard.borderRight + Style.space(12)
              spacing: Style.space(10)

              Item {
                id: imageSlot
                Layout.preferredWidth: Style.space(32)
                Layout.preferredHeight: Style.space(32)
                Layout.alignment: Qt.AlignVCenter
                // Hide on icon load failure so unresolved themed-icon names
                // don't render Qt's broken-image placeholder.
                visible: (rowCard.hasIcon || rowCard.hasMedia) && rowIconImage.status !== Image.Error

                Image {
                  id: rowIconImage
                  anchors.fill: parent
                  source: rowCard.hasMedia ? rowCard.image : rowCard.smallIconSource
                  fillMode: rowCard.hasMedia ? Image.PreserveAspectCrop : Image.PreserveAspectFit
                  sourceSize.width: imageSlot.width * Screen.devicePixelRatio
                  sourceSize.height: imageSlot.height * Screen.devicePixelRatio
                  asynchronous: true
                  smooth: true
                }
              }

              ColumnLayout {
                Layout.fillWidth: true
                spacing: Style.space(2)

                RowLayout {
                  Layout.fillWidth: true
                  spacing: Style.space(6)

                  Text {
                    Layout.fillWidth: true
                    visible: rowCard.summary.length > 0
                    text: rowCard.summary
                    font.family: root.bar ? root.bar.fontFamily : ""
                    color: root.colForeground
                    font.pixelSize: Style.font.subtitle
                    font.bold: true
                    wrapMode: Text.WordWrap
                    elide: Text.ElideRight
                    maximumLineCount: 1
                  }

                  Text {
                    text: NotificationLogic.relativeTime(rowCard.timestamp, popup.open ? Date.now() : 0)
                    font.family: root.bar ? root.bar.fontFamily : ""
                    color: root.colDim
                    font.pixelSize: Style.font.caption
                  }
                }

                Text {
                  Layout.fillWidth: true
                  visible: rowCard.sanitizedBody.length > 0
                  text: rowCard.sanitizedBody
                  font.family: root.bar ? root.bar.fontFamily : ""
                  textFormat: Text.PlainText
                  color: root.colDim
                  font.pixelSize: Style.font.bodySmall
                  wrapMode: Text.WordWrap
                  elide: Text.ElideRight
                  maximumLineCount: 2
                }
              }

              Rectangle {
                Layout.preferredWidth: Style.space(18)
                Layout.preferredHeight: Style.space(18)
                Layout.alignment: Qt.AlignVCenter
                radius: Math.min(4, root.cardRadius)
                color: rowCloseArea.containsMouse ? root.colBorder : "transparent"

                Text {
                  anchors.centerIn: parent
                  text: "✕"
                  font.family: root.bar ? root.bar.fontFamily : ""
                  color: root.colDim
                  font.pixelSize: Style.font.bodySmall
                }

                MouseArea {
                  id: rowCloseArea
                  anchors.fill: parent
                  hoverEnabled: true
                  cursorShape: Qt.PointingHandCursor
                  onClicked: root.dismissHistoryRow(rowCard.index)
                }
              }
            }
          }
        }

        // ----------------------------------------- notification empty state
        Item {
          Layout.fillWidth: true
          Layout.fillHeight: true
          visible: root.activeTab === "notifications" && historyModel.count === 0

          ColumnLayout {
            anchors.centerIn: parent
            spacing: Style.space(6)

            Text {
              Layout.alignment: Qt.AlignHCenter
              text: "󰂚"
              font.family: root.bar ? root.bar.fontFamily : ""
              color: root.colBorder
              font.pixelSize: Style.font.displayLarge
            }

            Text {
              Layout.alignment: Qt.AlignHCenter
              text: "Nothing recent"
              font.family: root.bar ? root.bar.fontFamily : ""
              color: root.colDim
              font.pixelSize: Style.font.body
            }
          }
        }

        // ----------------------------------------- reminder list
        ListView {
          id: reminderList
          Layout.fillWidth: true
          Layout.fillHeight: true
          clip: true
          spacing: Style.space(8)
          model: remindersModel
          visible: root.activeTab === "reminders" && count > 0

          delegate: BorderSurface {
            id: remCard
            required property int index
            required property string unit
            required property string message
            required property string label
            required property int minutes
            required property double at

            readonly property bool editing: root.editingUnit === remCard.unit

            width: reminderList.width
            implicitHeight: (editing ? editBox.implicitHeight : viewRow.implicitHeight) + Style.spacing.panelGap
            radius: root.cardRadius
            color: "transparent"
            borderSpec: Border.flat(editing ? root.colAccent : root.colBorder, Style.normalBorderWidth)

            // Declared first so the later close / chip children keep their clicks.
            MouseArea {
              anchors.fill: parent
              enabled: !remCard.editing
              cursorShape: Qt.PointingHandCursor
              onClicked: root.beginEdit(remCard.unit, remCard.at)
            }

            RowLayout {
              id: viewRow
              visible: !remCard.editing
              anchors.left: parent.left
              anchors.right: parent.right
              anchors.verticalCenter: parent.verticalCenter
              anchors.leftMargin: remCard.borderLeft + Style.space(12)
              anchors.rightMargin: remCard.borderRight + Style.space(12)
              spacing: Style.space(10)

              Text {
                Layout.alignment: Qt.AlignVCenter
                text: "󰢌"
                font.family: root.bar ? root.bar.fontFamily : ""
                color: root.colDim
                font.pixelSize: Style.font.subtitle
              }

              ColumnLayout {
                Layout.fillWidth: true
                spacing: Style.space(2)

                Text {
                  Layout.fillWidth: true
                  text: remCard.label.length > 0 ? remCard.label : remCard.minutes + "-min reminder"
                  font.family: root.bar ? root.bar.fontFamily : ""
                  textFormat: Text.PlainText
                  color: root.colForeground
                  font.pixelSize: Style.font.subtitle
                  font.bold: true
                  elide: Text.ElideRight
                  maximumLineCount: 1
                }

                Text {
                  Layout.fillWidth: true
                  text: "in " + NotificationLogic.remainingLabel(remCard.at, root.nowMs)
                    + " · " + NotificationLogic.reminderTimeLabel(remCard.at, root.nowMs)
                  font.family: root.bar ? root.bar.fontFamily : ""
                  color: root.colDim
                  font.pixelSize: Style.font.bodySmall
                  elide: Text.ElideRight
                  maximumLineCount: 1
                }
              }

              Rectangle {
                Layout.preferredWidth: Style.space(18)
                Layout.preferredHeight: Style.space(18)
                Layout.alignment: Qt.AlignVCenter
                radius: Math.min(4, root.cardRadius)
                color: remCloseArea.containsMouse ? root.colBorder : "transparent"

                Text {
                  anchors.centerIn: parent
                  text: "✕"
                  font.family: root.bar ? root.bar.fontFamily : ""
                  color: root.colDim
                  font.pixelSize: Style.font.bodySmall
                }

                MouseArea {
                  id: remCloseArea
                  anchors.fill: parent
                  hoverEnabled: true
                  cursorShape: Qt.PointingHandCursor
                  onClicked: root.cancelReminder(remCard.unit)
                }
              }
            }

            ColumnLayout {
              id: editBox
              visible: remCard.editing
              anchors.left: parent.left
              anchors.right: parent.right
              anchors.verticalCenter: parent.verticalCenter
              anchors.leftMargin: remCard.borderLeft + Style.space(12)
              anchors.rightMargin: remCard.borderRight + Style.space(12)
              spacing: Style.space(4)

              // Seeding text imperatively rather than binding it: the field owns
              // its text once the user types, and a binding would fight that.
              onVisibleChanged: if (visible) {
                editField.text = root.editWhen
                editField.forceActiveFocus()
                editField.selectAll()
              }

              RowLayout {
                Layout.fillWidth: true
                spacing: Style.space(8)

                TextField {
                  id: editField
                  Layout.fillWidth: true
                  Layout.alignment: Qt.AlignVCenter
                  placeholderText: "45m or 14:30"
                  foreground: root.colForeground
                  accent: root.colAccent
                  font.pixelSize: Style.font.bodySmall
                  verticalPadding: Style.spacing.xs
                  onAccepted: editSave.commit()
                  Keys.onEscapePressed: root.editingUnit = ""
                }

                Button {
                  id: editSave
                  Layout.alignment: Qt.AlignVCenter
                  text: "Save"
                  bordered: true
                  enabled: NotificationLogic.parseWhen(editField.text, root.nowMs) > 0
                  opacity: enabled ? 1 : 0.45
                  foreground: root.colForeground
                  accent: root.colAccent
                  fontFamily: root.bar ? root.bar.fontFamily : ""
                  fontSize: Style.font.caption
                  verticalPadding: Style.spacing.xs

                  function commit() {
                    if (!enabled) return
                    var minutes = NotificationLogic.parseWhen(editField.text, Date.now())
                    root.rescheduleReminder(remCard.unit, minutes, remCard.message)
                    root.editingUnit = ""
                  }

                  onClicked: commit()
                }

                Button {
                  Layout.alignment: Qt.AlignVCenter
                  text: "Cancel"
                  foreground: root.colForeground
                  accent: root.colAccent
                  fontFamily: root.bar ? root.bar.fontFamily : ""
                  fontSize: Style.font.caption
                  verticalPadding: Style.spacing.xs
                  onClicked: root.editingUnit = ""
                }
              }

              Text {
                Layout.fillWidth: true
                text: NotificationLogic.whenHint(editField.text, root.nowMs)
                font.family: root.bar ? root.bar.fontFamily : ""
                color: root.colDim
                font.pixelSize: Style.font.caption
                elide: Text.ElideRight
                maximumLineCount: 1
              }
            }
          }
        }

        // ----------------------------------------- reminder empty state
        Item {
          Layout.fillWidth: true
          Layout.fillHeight: true
          visible: root.activeTab === "reminders" && remindersModel.count === 0

          ColumnLayout {
            anchors.centerIn: parent
            spacing: Style.space(6)

            Text {
              Layout.alignment: Qt.AlignHCenter
              text: "󰢌"
              font.family: root.bar ? root.bar.fontFamily : ""
              color: root.colBorder
              font.pixelSize: Style.font.displayLarge
            }

            Text {
              Layout.alignment: Qt.AlignHCenter
              text: "No reminders set"
              font.family: root.bar ? root.bar.fontFamily : ""
              color: root.colDim
              font.pixelSize: Style.font.body
            }
          }
        }

        // ----------------------------------------- reminder compose row
        ColumnLayout {
          visible: root.activeTab === "reminders"
          Layout.fillWidth: true
          spacing: Style.space(4)

          RowLayout {
            Layout.fillWidth: true
            spacing: Style.space(8)

            TextField {
              id: composeWhen
              Layout.preferredWidth: Style.space(96)
              Layout.alignment: Qt.AlignVCenter
              placeholderText: "45m or 14:30"
              foreground: root.colForeground
              accent: root.colAccent
              font.pixelSize: Style.font.bodySmall
              verticalPadding: Style.spacing.xs
              onAccepted: composeSet.commit()
              Keys.onEscapePressed: root.close()
            }

            TextField {
              id: composeMessage
              Layout.fillWidth: true
              Layout.alignment: Qt.AlignVCenter
              placeholderText: "Remind me to…"
              foreground: root.colForeground
              accent: root.colAccent
              font.pixelSize: Style.font.bodySmall
              verticalPadding: Style.spacing.xs
              onAccepted: composeSet.commit()
              Keys.onEscapePressed: root.close()
            }

            Button {
              id: composeSet
              Layout.alignment: Qt.AlignVCenter
              text: "Set"
              bordered: true
              enabled: NotificationLogic.parseWhen(composeWhen.text, root.nowMs) > 0
              opacity: enabled ? 1 : 0.45
              foreground: root.colForeground
              accent: root.colAccent
              fontFamily: root.bar ? root.bar.fontFamily : ""
              fontSize: Style.font.caption
              verticalPadding: Style.spacing.xs

              function commit() {
                if (!enabled) return
                var minutes = NotificationLogic.parseWhen(composeWhen.text, Date.now())
                if (!root.createReminder(minutes, composeMessage.text)) return
                composeWhen.text = ""
                composeMessage.text = ""
                composeWhen.forceActiveFocus()
              }

              onClicked: commit()
            }
          }

          Text {
            Layout.fillWidth: true
            text: NotificationLogic.whenHint(composeWhen.text, root.nowMs)
            font.family: root.bar ? root.bar.fontFamily : ""
            color: root.colDim
            font.pixelSize: Style.font.caption
            elide: Text.ElideRight
            maximumLineCount: 1
          }
        }
      }
    }
  }
}
