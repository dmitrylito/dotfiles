# Test Hyprland in the testbed, never in Dmitry's session

Anything that opens, moves, resizes or focuses a window, changes a workspace, or
reloads Hyprland config goes through `hypr-testbed` first. Driving the live session
interrupts his work and has twice left stray windows behind. This is not negotiable
for exploratory testing — only a final confirmation runs against the live session,
and only after he says so.

    hypr-testbed start [monitors]   # 3 by default, ws 1/2/3 one per monitor
    eval "$(hypr-testbed env)"      # points hyprctl, launched apps and Chromium at it
    hypr-testbed run <cmd...>       # or one command at a time
    hypr-testbed status
    hypr-testbed stop               # always, when done

- A running testbed has **no window in the host session** — it removes its own
  nested window once the virtual monitors exist. `HYPR_TESTBED_VISIBLE=1` keeps it
  (parked on host workspace 9) when the point is to watch it.
- **Chromium works in it.** The testbed exports `CHROMIUM_USER_DATA_DIR`, seeded with
  the real profile names so every derived WM_CLASS matches the real session.
  `work-mode` has been run end to end inside it. Signing in there is a separate
  Chromium profile tree — expect login walls, not the real session's tabs.
- **Other singletons still escape:** Spotify, for one, hands the launch to the
  instance already running in the host session and no window appears in the testbed.
  Use a stand-in (`foot --app-id=<the class>`) for those.
- It needs a host Wayland session (aquamarine 0.15.1 has no headless-only backend),
  so it cannot run over a bare SSH shell.
- `hyprctl` needs the right `HYPRLAND_INSTANCE_SIGNATURE`: the runtime directory
  keeps dead sessions' signatures and some still have a live-looking socket. Probe
  candidates with `hyprctl version`; never assume the newest or the inherited one.

Config lives in `~/.config/hypr/*.lua` (chezmoi source `dot_config/hypr/`), which is
Lua, not the old syntax: options go through `hl.config({ general = …, dwindle = … })`,
and `Hyprland --verify-config -c <file>` checks a file without running it.
