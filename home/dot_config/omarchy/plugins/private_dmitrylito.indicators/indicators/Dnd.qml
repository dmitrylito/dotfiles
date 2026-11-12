import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

// A bar-widget gets no first-party service proxies (omarchy only hands those to
// kind "bar" plugins), so this asks the notifications service over IPC.
// Polls call the handler in-process through IpcRegistry: every omarchy-shell
// call leaves a Socket in the shell that is only freed at exit, and a day of
// 3s polls made shell restarts (omarchy update) hang for minutes.
BarIndicator {
  id: root

  property bool dnd: false

  active: dnd
  activeText: "󰂛"
  inactiveText: "󰂛"
  activeTooltipText: "Allow Notifications"
  inactiveTooltipText: "Silence Notifications"

  function refresh() {
    if (setProc.running) return
    var result = IpcRegistry.call("notifications", "isDnd", [])
    var state = result.ran ? result.output.trim() : ""
    if (state === "on" || state === "off") root.dnd = state === "on"
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
