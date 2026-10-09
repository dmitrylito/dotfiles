import QtQuick
import Quickshell
import Quickshell.Io
import qs.Ui

// omarchy.idle is disabled on this host, so its service is gone; the state lives
// in the file omarchy-toggle-idle writes, which dmitrylito.display-idle honors.
BarIndicator {
  id: root

  property bool stayAwake: false

  active: stayAwake
  activeText: "󰅶"
  inactiveText: "󰅶"
  activeTooltipText: "Allow Idle Lock & Screensaver"
  inactiveTooltipText: "Stay Awake"

  function refresh() {
    if (!statusProc.running) statusProc.running = true
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
    command: ["omarchy-toggle-idle", "status"]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        try { root.stayAwake = !!JSON.parse(text).enabled } catch (e) {}
      }
    }
  }

  onPressed: function() {
    root.stayAwake = !root.stayAwake
    Quickshell.execDetached(["omarchy-toggle-idle", root.stayAwake ? "stay-awake" : "allow-idle"])
  }
}
