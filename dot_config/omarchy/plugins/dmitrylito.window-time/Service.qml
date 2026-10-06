import QtQuick
import Quickshell
import Quickshell.Wayland

// Feeds idle state to the window-time tracker (~/.local/bin/window-time), so time
// away from the keyboard is not counted toward the focused window. Inhibitors
// (video playing) hold idle off, so watching something still counts.
Item {
  id: root

  readonly property int idleSeconds: 120

  function run(command) {
    Quickshell.execDetached(["bash", "-lc", command])
  }

  IdleMonitor {
    timeout: root.idleSeconds
    respectInhibitors: true
    onIsIdleChanged: root.run(isIdle ? "window-time idle " + root.idleSeconds : "window-time active")
  }
}
