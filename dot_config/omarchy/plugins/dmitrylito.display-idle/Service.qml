import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Wayland

// Stands in for omarchy.idle (disabled in shell.json): this host never locks
// or sleeps, so idle only blanks the displays and activity brings them back.
Item {
  id: root

  readonly property int displayOffSeconds: 300

  // Stay Awake (omarchy-toggle-idle, the bar indicator) is a marker file.
  readonly property string stayAwakePath: Quickshell.env("HOME") + "/.local/state/omarchy/indicators/stay-awake"
  property bool stayAwake: false

  // omarchy-system-wake re-enables every output, including a laptop panel
  // under a closed lid, so that panel is blanked again afterwards.
  readonly property string wakeCommand: "omarchy-system-wake; omarchy-hw-laptop-closed && hyprctl dispatch 'hl.dsp.dpms({ action = \"disable\", monitor = \"eDP-1\" })'"

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
}
