import QtQuick
import Quickshell
import Quickshell.Io
import qs.Ui

// A bar-widget gets no first-party service proxies (omarchy only hands those to
// kind "bar" plugins), so this talks to the nightlight service over IPC.
BarIndicator {
  id: root

  property bool enabledNow: false
  // The temperature applies asynchronously; a poll right after a click still
  // reports the old state.
  property double holdUntil: 0

  active: enabledNow
  activeText: "󰔎"
  inactiveText: "󰔎"
  activeTooltipText: "Day Light"
  inactiveTooltipText: "Night Light"

  function refresh() {
    if (!statusProc.running && Date.now() >= holdUntil) statusProc.running = true
  }

  function toggle() {
    enabledNow = !enabledNow
    holdUntil = Date.now() + 1500
    Quickshell.execDetached(["omarchy-shell", "-q", "nightlight", enabledNow ? "enable" : "disable"])
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
    id: statusProc
    command: ["omarchy-shell", "nightlight", "status"]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        if (Date.now() < root.holdUntil) return
        try { root.enabledNow = !!JSON.parse(text).enabled } catch (e) {}
      }
    }
  }

  onPressed: function() { root.toggle() }
}
