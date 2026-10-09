import QtQuick
import Quickshell
import Quickshell.Io
import qs.Ui

// A bar-widget gets no first-party service proxies (omarchy only hands those to
// kind "bar" plugins), so this asks the notifications service over IPC.
BarIndicator {
  id: root

  property bool dnd: false

  active: dnd
  activeText: "󰂛"
  inactiveText: "󰂛"
  activeTooltipText: "Allow Notifications"
  inactiveTooltipText: "Silence Notifications"

  function refresh() {
    if (!stateProc.running && !setProc.running) stateProc.running = true
  }

  Component.onCompleted: refresh()

  Connections {
    target: root.indicatorHost
    ignoreUnknownSignals: true
    function onRefreshRequested() { root.refresh() }
  }

  Timer {
    interval: 3000
    running: true
    repeat: true
    onTriggered: root.refresh()
  }

  Process {
    id: stateProc
    command: ["omarchy-shell", "notifications", "dndState"]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        var state = String(text).trim()
        if (state === "on" || state === "off") root.dnd = state === "on"
      }
    }
  }

  Process {
    id: setProc
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        var state = String(text).trim()
        if (state === "on" || state === "off") root.dnd = state === "on"
      }
    }
  }

  onPressed: function() {
    if (setProc.running) return
    root.dnd = !root.dnd
    setProc.command = ["omarchy-shell", "notifications", "setDnd", root.dnd ? "on" : "off"]
    setProc.running = true
  }
}
