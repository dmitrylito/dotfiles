import QtQuick
import Quickshell
import Quickshell.Wayland

// Feeds idle state to the window-time tracker (~/.local/bin/window-time), so time
// away from the keyboard is not counted toward the focused window. Input only:
// an open Meet or video tab inhibits idle indefinitely, even when nobody is
// there. The tracker records which window was inhibiting ("watching") and keeps
// counting through calls by itself, from the microphone.
Item {
  id: root

  readonly property int idleSeconds: 120

  function run(command) {
    Quickshell.execDetached(["bash", "-lc", command])
  }

  IdleMonitor {
    timeout: root.idleSeconds
    respectInhibitors: false
    onIsIdleChanged: root.run(isIdle ? "window-time idle " + root.idleSeconds : "window-time active")
  }
}
