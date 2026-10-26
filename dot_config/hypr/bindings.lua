-- ---------------------------------------------------------------------------
-- Unbinds
-- ---------------------------------------------------------------------------

-- Omarchy defaults deliberately disabled (vim-style HJKL is used instead of
-- arrows) or replaced by a binding below.
local unbinds = {
	"SUPER + LEFT",
	"SUPER + RIGHT",
	"SUPER + UP",
	"SUPER + DOWN",
	"SUPER + ALT + LEFT",
	"SUPER + ALT + RIGHT",
	"SUPER + ALT + UP",
	"SUPER + ALT + DOWN",
	"SUPER + SHIFT + LEFT",
	"SUPER + SHIFT + RIGHT",
	"SUPER + SHIFT + UP",
	"SUPER + SHIFT + DOWN",
	"SUPER + CTRL + X",
	"ALT + Alt_R",
	"SUPER + J",
	"SUPER + K",
	"SUPER + L",
	"SUPER + ALT + K",
	"SUPER + ALT + RETURN",
	"SUPER + RETURN",
	"SUPER + SHIFT + M",
	"SUPER + SHIFT + D",
	"SUPER + SHIFT + Y",
}

-- Omarchy preinstalled app/web-app defaults that are not used on this system.
-- Keep these explicit so package updates cannot silently restore stale shortcuts.
local unused_default_app_bindings = {
	"SUPER + SHIFT + ALT + M", -- Music TUI (cliamp is not installed)
	"SUPER + SHIFT + G", -- Signal
	"SUPER + SHIFT + O", -- Obsidian
	"SUPER + SHIFT + SLASH", -- 1Password
	"SUPER + SHIFT + ALT + A", -- Grok
	"SUPER + SHIFT + C", -- HEY Calendar
	"SUPER + SHIFT + E", -- HEY Email
	"SUPER + SHIFT + ALT + E", -- HEY New email
	"SUPER + SHIFT + ALT + G", -- WhatsApp
	"SUPER + SHIFT + CTRL + G", -- Google Messages
	"SUPER + SHIFT + P", -- Google Photos
	"SUPER + SHIFT + S", -- Google Maps
}

for _, keys in ipairs(unbinds) do
	hl.unbind(keys)
end
for _, keys in ipairs(unused_default_app_bindings) do
	hl.unbind(keys)
end

-- ---------------------------------------------------------------------------
-- Applications
-- ---------------------------------------------------------------------------

local terminal = 'xdg-terminal-exec --dir="$(omarchy-cmd-terminal-cwd)"'

o.bind("SUPER + ALT + RETURN", "Terminal", { launch = terminal })
o.bind("SUPER + semicolon", "Terminal", { launch = terminal })
-- Remote, not local: with a local herdr the client owns prefix mode, so the server-side
-- [[keys.command]] popups (prefix+g lazygit, prefix+u urls) never fire.
o.bind(
	"SUPER + B",
	"Herdr remote (choose SSH target)",
	{ launch = "xdg-terminal-exec ~/.local/bin/herdr-remote-picker" }
)
-- o.rebind("SUPER + SHIFT + F", "File manager", { tui = "yazi", focus = true }) -- yazi over the default nautilus, which hardcodes dot entries to sort last
o.bind("SUPER + SHIFT + D", "Discord", 'omarchy-launch-or-focus ^discord$ "uwsm-app -- discord.desktop"')
o.bind("SUPER + SHIFT + Y", "YouTube", 'omarchy-launch-webapp "https://youtube.com/" --profile-directory="Default"')

-- ---------------------------------------------------------------------------
-- Window focus and movement
-- ---------------------------------------------------------------------------

o.bind("SUPER + H", "Focus left window", hl.dsp.focus({ direction = "l" }))
o.bind("SUPER + J", "Focus next window", hl.dsp.focus({ direction = "d" }))
o.bind("SUPER + K", "Focus previous window", hl.dsp.focus({ direction = "u" }))
o.bind("SUPER + L", "Focus right window", hl.dsp.focus({ direction = "r" }))

o.bind("SUPER + SHIFT + H", "Swap window to the left", hl.dsp.window.swap({ direction = "l" }))
o.bind("SUPER + SHIFT + J", "Swap window down", hl.dsp.window.swap({ direction = "d" }))
o.bind("SUPER + SHIFT + K", "Swap window up", hl.dsp.window.swap({ direction = "u" }))
o.bind("SUPER + SHIFT + L", "Swap window to the right", hl.dsp.window.swap({ direction = "r" }))

o.bind("SUPER + ALT + H", "Move window to group on right", "hyprctl dispatch moveintogroup r")
o.bind("SUPER + ALT + J", "Move window to group on bottom", "hyprctl dispatch moveintogroup d")
o.bind("SUPER + ALT + K", "Move window to group on top", "hyprctl dispatch moveintogroup u")
o.bind("SUPER + ALT + L", "Move window to group on left", "hyprctl dispatch moveintogroup l")

o.bind("SUPER + N", "Toggle window split", hl.dsp.layout("togglesplit"))

-- ---------------------------------------------------------------------------
-- Editing
-- ---------------------------------------------------------------------------

-- Copies of Omarchy's clipboard helpers (default/hypr/bindings/clipboard.lua),
-- which are local to that file. send_key_state down/up instead of send_shortcut works
-- around Hyprland leaving synthetic keys stuck.
local function send_shortcut_once(mods, key)
	hl.dispatch(hl.dsp.send_key_state({ mods = mods, key = key, state = "down" }))
	hl.timer(function()
		hl.dispatch(hl.dsp.send_key_state({ mods = mods, key = key, state = "up" }))
	end, { timeout = 50, type = "oneshot" })
end

local function active_window_is_terminal()
	local window = hl.get_active_window()
	for _, tag in ipairs(window and window.tags or {}) do
		if tag:gsub("%*$", "") == "terminal" then
			return true
		end
	end
	return false
end

-- SUPER + A (Select all) comes from Omarchy's clipboard.lua.
-- Not sent to terminals: Ctrl+Z there suspends the foreground job.
o.bind("SUPER + Z", "Undo", function()
	if not active_window_is_terminal() then
		send_shortcut_once("CTRL", "Z")
	end
end)

-- ---------------------------------------------------------------------------
-- Pop-out
-- ---------------------------------------------------------------------------

local popout = require("hypr.popout")

hl.unbind("SUPER + U")
hl.bind("SUPER + U", popout.toggle, { description = "Toggle window pop-out (centered 16:10 float)" })
hl.unbind("SUPER + SHIFT + U")
hl.bind(
	"SUPER + SHIFT + U",
	hl.dsp.exec_cmd(os.getenv("HOME") .. "/.config/hypr/scripts/toggle-popout.sh"),
	{ description = "Toggle window pop-out (Bash fallback)" }
)

local pseudopanel = require("hypr.pseudopanel")

hl.unbind("SUPER + P") -- Omarchy default: Pseudo window
hl.bind("SUPER + P", pseudopanel.toggle, {
	description = "Toggle pseudo panel (centered 16:10, tiles when a window joins)",
})

-- ---------------------------------------------------------------------------
-- Scratchpads
-- ---------------------------------------------------------------------------

require("hypr.qconsole")

local function qconsole_toggle()
	-- on_created_empty only fires for an empty scratchpad; with the herdr window
	-- still there, restart the agent if it was exited.
	for _, window in ipairs(hl.get_windows({ class = "org.omarchy.agent" })) do
		if window.workspace and window.workspace.name == "special:qconsole" then
			hl.exec_cmd("herdr-agent --ensure")
			break
		end
	end
	hl.dispatch(hl.dsp.workspace.toggle_special("qconsole"))
end

-- Focusing a window on a hidden special workspace does not reveal it, so toggle the
-- workspace; chezmoi.lua's rule is silent (work-mode needs that), so a cold launch
-- must be revealed here once the window exists.
-- get_windows' class filter is a substring match, not a regex.
local function spotify_reveal_when_mapped(attempts)
	if #hl.get_windows({ class = "spotify" }) > 0 then
		hl.dispatch(hl.dsp.workspace.toggle_special("spotify"))
		return
	end
	if attempts <= 0 then
		return
	end
	hl.timer(function()
		spotify_reveal_when_mapped(attempts - 1)
	end, { timeout = 250, type = "oneshot" })
end

local function spotify_toggle()
	if #hl.get_windows({ class = "spotify" }) == 0 then
		hl.exec_cmd(o.launch("spotify"))
		spotify_reveal_when_mapped(80)
		return
	end
	hl.dispatch(hl.dsp.workspace.toggle_special("spotify"))
end

-- Omarchy moved the console to special:qconsole on Super+Grave and left Super+S a
-- plain scratchpad; Super+S stays the console here.
hl.unbind("SUPER + S") -- Omarchy default: Toggle scratchpad
hl.bind("SUPER + S", qconsole_toggle, { description = "Toggle Quake console" })
-- omarchy-shell instead of { ipc = ... }: Omarchy 4.0.4's o.bind has no ipc branch and
-- passes the table to hl.bind, which rejects it (helpers.lua:105).
o.bind("SUPER + E", "Toggle notification center", "omarchy-shell -q shell toggle omacom.notification-center")
o.bind("SUPER + D", "Toggle Spotify scratchpad", spotify_toggle)
o.bind("SUPER + SHIFT + M", "Music", spotify_toggle)

o.bind("SUPER + ALT + A", "Move window to AI", hl.dsp.window.move({ workspace = "special:AI", follow = false }))
o.bind(
	"SUPER + ALT + D",
	"Move window to Spotify",
	hl.dsp.window.move({ workspace = "special:spotify", follow = false })
)

-- ---------------------------------------------------------------------------
-- Dictation
-- ---------------------------------------------------------------------------

local dictation_tap_window_ms = 300
local dictation_tap_generation = 0
local dictation_tap_armed = false
local voxtype_state_file = (os.getenv("XDG_RUNTIME_DIR") or "") .. "/voxtype/state"

local function dictation_is_recording()
	local file = io.open(voxtype_state_file, "r")
	if not file then
		return false
	end
	local state = file:read("*l")
	file:close()
	return state == "recording" or state == "streaming"
end

local function dictation_super_tap()
	if dictation_is_recording() then
		dictation_tap_armed = false
		hl.exec_cmd("voxtype record stop")
		return
	end
	if dictation_tap_armed then
		dictation_tap_armed = false
		hl.exec_cmd("voxtype record start")
		return
	end
	dictation_tap_armed = true
	dictation_tap_generation = dictation_tap_generation + 1
	local generation = dictation_tap_generation
	-- A stale timer from an earlier tap must not disarm a newer one.
	hl.timer(function()
		if generation == dictation_tap_generation then
			dictation_tap_armed = false
		end
	end, { timeout = dictation_tap_window_ms, type = "oneshot" })
end

-- A modifier's mask changes between its press and release, so match the keysym
-- independently of it (same as Omarchy's ALT + Alt_R push-to-talk).
o.bind("SUPER + Super_L", "Dictation (double-tap Super to start, tap to stop)", dictation_super_tap, {
	release = true,
	ignore_mods = true,
})
o.bind("RETURN", "Stop dictation", "voxtype record stop", { non_consuming = true }) -- re-added after omarchy's region picker tears down; see chezmoi.lua

-- ---------------------------------------------------------------------------
-- System
-- ---------------------------------------------------------------------------

o.bind("SUPER + M", "Show key bindings", "omarchy-menu-keybindings")
o.bind("SUPER + CTRL + ALT + L", "Suspend", "systemctl suspend", { locked = true })

-- This host never sleeps or locks (system/install-never-sleep.sh): closing the
-- lid only blanks the panel. Omarchy's lid-close bind is replaced because it
-- locks when no external monitor is connected; its lid-open bind still runs.
hl.unbind("switch:on:Lid Switch")
o.bind(
	"switch:on:Lid Switch",
	nil,
	'omarchy-hyprland-monitor-clamshell; hyprctl dispatch \'hl.dsp.dpms({ action = "disable", monitor = "eDP-1" })\'',
	{ locked = true }
)
o.bind("switch:off:Lid Switch", nil, hl.dsp.dpms({ action = "enable", monitor = "eDP-1" }), { locked = true })
