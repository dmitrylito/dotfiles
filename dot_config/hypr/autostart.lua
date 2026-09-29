-- hyprsunset is not autostarted: the identity profile in hyprsunset.conf already
-- cancels its default tint, and toggling nightlight starts it on demand.
o.launch_on_start("solaar --window=hide")
o.exec_on_start("/usr/lib/kdeconnectd")
o.exec_on_start("/usr/bin/kdeconnect-indicator")
o.exec_on_start("hyprctl dispatch workspace 1")
