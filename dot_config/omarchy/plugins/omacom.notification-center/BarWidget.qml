// Bell bar widget: recent-notification list + DND toggle for the Omarchy 4
// notifications service. History lives on disk (one JSON file per entry under
// the service's historyDir); live toasts come from service.popupModel.
// Left-click (or `omarchy-shell notification-center toggle`) opens the list,
// right-click toggles Do Not Disturb.

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

  onPopupOpenChanged: if (popupOpen) refreshHistory()

  // Look up the long-running notifications service through the shell host.
  readonly property var hostShell: bar && bar.shell ? bar.shell : null
  readonly property var notificationService: hostShell?.firstPartyServiceFor("omarchy.notifications")

  readonly property int liveCount: notificationService ? notificationService.popupModel.count : 0
  readonly property bool dnd: notificationService ? notificationService.doNotDisturb : false
  readonly property string historyDir: notificationService ? notificationService.historyDir : ""
  readonly property string imagesDir: notificationService ? notificationService.imagesDir : ""

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
  readonly property int cardRadius: notificationService ? notificationService.cornerRadius : 0

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

  function clearAll() {
    if (notificationService) notificationService.clearHistory()
    historyModel.clear()
  }

  // A toast leaving the screen is archived into historyDir through the
  // service's async file queue — re-read shortly after so an open popup
  // picks it up once the move has landed.
  Connections {
    target: root.notificationService ? root.notificationService.popupModel : null
    function onCountChanged() { if (root.popupOpen) refreshTimer.restart() }
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
    id: removeProc
    running: false
    onExited: root.runNextRemove()
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
        if (root.notificationService) {
          root.notificationService.setDoNotDisturb(!root.notificationService.doNotDisturb)
        }
      } else {
        root.popupOpen = !root.popupOpen
      }
    }
  }

  PopupCard {
    id: popup
    anchorItem: button
    bar: root.bar
    owner: root
    open: root.popupOpen
    contentWidth: popup.fittedContentWidth(Style.space(440))
    contentHeight: popup.cappedContentHeight(Style.space(540))

    ColumnLayout {
      anchors.fill: parent
      spacing: Style.space(10)

      // ----------------------------------------- header
      RowLayout {
        Layout.fillWidth: true
        spacing: Style.space(8)

        Text {
          text: "Notifications"
          font.family: root.bar ? root.bar.fontFamily : ""
          color: root.colForeground
          font.pixelSize: Style.font.title
          font.bold: true
        }

        Item { Layout.fillWidth: true }

        BorderSurface {
          id: dndPill
          Layout.preferredHeight: Math.max(Style.space(24), Style.font.bodySmall + Style.spacing.controlPaddingY * 2)
          Layout.preferredWidth: dndLabel.implicitWidth + dndGlyph.implicitWidth + Style.space(18)
          radius: Math.min(Style.space(12), root.cardRadius + Style.space(6))
          color: dndOn ? root.colAccent : root.colSurface
          borderSpec: Border.flat(dndOn ? root.colAccent : root.colBorder, Style.normalBorderWidth)

          readonly property bool dndOn: !!root.notificationService && root.notificationService.doNotDisturb

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
            onClicked: if (root.notificationService) root.notificationService.setDoNotDisturb(!dndPill.dndOn)
          }
        }
      }

      // ----------------------------------------- action row
      RowLayout {
        Layout.fillWidth: true
        visible: historyModel.count > 0
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

      // ----------------------------------------- list
      ListView {
        id: listView
        Layout.fillWidth: true
        Layout.fillHeight: true
        clip: true
        spacing: Style.space(8)
        model: historyModel
        visible: count > 0

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

      // ----------------------------------------- empty state
      Item {
        Layout.fillWidth: true
        Layout.fillHeight: true
        visible: historyModel.count === 0

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
    }
  }
}
