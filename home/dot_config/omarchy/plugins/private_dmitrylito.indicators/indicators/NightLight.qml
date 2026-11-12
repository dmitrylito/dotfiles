import QtQuick
import Quickshell
import qs.Commons
import qs.Ui

// A bar-widget gets no first-party service proxies (omarchy only hands those to
// kind "bar" plugins), so this talks to the nightlight service over IPC.
// Polls call the handler in-process through IpcRegistry: every omarchy-shell
// call leaves a Socket in the shell that is only freed at exit, and a day of
// 3s polls made shell restarts (omarchy update) hang for minutes.
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
    if (Date.now() < holdUntil) return
    var result = IpcRegistry.call("nightlight", "status", [])
    if (!result.ran) return
    try { enabledNow = !!JSON.parse(result.output).enabled } catch (e) {}
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

  onPressed: function() { root.toggle() }
}
