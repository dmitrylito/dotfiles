# Test Hyprland in the testbed, never in Dmitry's session

Anything that opens, moves, resizes or focuses a window, changes a workspace, or
reloads Hyprland config goes through `hypr-testbed` first. Driving the live session
interrupts his work and has twice left stray windows behind. This is not negotiable
for exploratory testing — only a final confirmation runs against the live session,
and only after he says so.

    hypr-testbed start [--headless] [monitors]   # 3 by default, ws 1/2/3 one per monitor
    eval "$(hypr-testbed env)"      # points hyprctl, launched apps and Chromium at it
    hypr-testbed run <cmd...>       # or one command at a time
    hypr-testbed screenshot [monitor|ws] [file]  # prints the PNG path
    hypr-testbed status
    hypr-testbed stop               # always, when done

- A running testbed keeps its nested window on a **hidden host scratchpad**;
  `HYPR_TESTBED_VISIBLE=1` parks it on host workspace 9 instead.
- **Screenshots never need `show`** — `show` puts the testbed on his screen. Monitor 1
  (WAYLAND-1) is that hidden window and cannot be captured; the HEADLESS monitors can.
  Start with `--headless` whenever the result has to be looked at, so every workspace
  is capturable. That includes the omarchy shell: run a second
  `quickshell -n -p <copy of $OMARCHY_PATH/shell>` with `HOME` pointed at a copied
  config and side-effect services (notifications, idle, lock, polkit) in
  `disabledPlugins`, and address it with `HOME=… quickshell -p <copy> ipc call …`.
- **Applying to the live session is a deploy, not a test.** Never use the live session
  to explore or debug. Once a fix has passed in the testbed, apply it (`chezmoi apply`
  of the changed targets, `omarchy restart shell` when a plugin changed) without asking
  — he said "dont ask to apply fixes" — and read back the shell log after.
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
