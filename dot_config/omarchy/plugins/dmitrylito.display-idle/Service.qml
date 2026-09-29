import QtQuick
import Quickshell
import Quickshell.Wayland

// Stands in for omarchy.idle (disabled in shell.json): this host never locks
// or sleeps, so idle only blanks the displays and activity brings them back.
Item {
  id: root

  readonly property int displayOffSeconds: 300

  // omarchy-system-wake re-enables every output, including a laptop panel
  // under a closed lid, so that panel is blanked again afterwards.
  readonly property string wakeCommand: "omarchy-system-wake; omarchy-hw-laptop-closed && hyprctl dispatch 'hl.dsp.dpms({ action = \"disable\", monitor = \"eDP-1\" })'"

  function run(command) {
    Quickshell.execDetached(["bash", "-lc", command])
  }

  IdleMonitor {
    id: idleMonitor
    timeout: root.displayOffSeconds
    respectInhibitors: true
    onIsIdleChanged: root.run(isIdle ? "omarchy-brightness-display off" : root.wakeCommand)
  }
}
