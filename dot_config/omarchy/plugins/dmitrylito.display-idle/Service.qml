import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Wayland

// Stands in for omarchy.idle (disabled in shell.json): no screensaver and no
// sleep; idle blanks the displays, then locks, and activity brings them back.
Item {
  id: root

  readonly property int displayOffSeconds: 600
  readonly property int lockSeconds: 900

  // Stay Awake (omarchy-toggle-idle, the bar indicator) is a marker file.
  readonly property string stayAwakePath: Quickshell.env("HOME") + "/.local/state/omarchy/indicators/stay-awake"
  property bool stayAwake: false

  // display-relink runs omarchy-system-wake, re-blanks a closed-lid laptop
  // panel, and re-trains an HDMI link amdgpu failed to bring up.
  readonly property string wakeCommand: "display-relink"

  function run(command) {
    Quickshell.execDetached(["bash", "-lc", command])
  }

  Process {
    id: stayAwakeProc
    command: ["test", "-e", root.stayAwakePath]
    onExited: function(exitCode) { root.stayAwake = exitCode === 0 }
  }

  Timer {
    interval: 3000
    running: true
    repeat: true
    triggeredOnStart: true
    onTriggered: if (!stayAwakeProc.running) stayAwakeProc.running = true
  }

  IdleMonitor {
    id: idleMonitor
    enabled: !root.stayAwake
    timeout: root.displayOffSeconds
    respectInhibitors: true
    onIsIdleChanged: root.run(isIdle ? "omarchy-brightness-display off" : root.wakeCommand)
  }

  IdleMonitor {
    enabled: !root.stayAwake
    timeout: root.lockSeconds
    respectInhibitors: true
    onIsIdleChanged: if (isIdle) root.run("omarchy-system-lock")
  }
}
