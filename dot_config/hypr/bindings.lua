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
o.bind("SUPER + B", "Herdr remote (choose SSH target)", { launch = "xdg-terminal-exec ~/.local/bin/herdr-remote-picker" })
o.rebind("SUPER + SHIFT + F", "File manager", { tui = "yazi", focus = true }) -- yazi over the default nautilus, which hardcodes dot entries to sort last
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

-- ---------------------------------------------------------------------------
-- Scratchpads
-- ---------------------------------------------------------------------------

-- Omarchy keeps one global geometry rule for the qconsole. On mixed-size
-- monitors that rule can still contain the previous monitor's bottom gap when
-- SUPER+S runs, so refit it synchronously against the monitor receiving the
-- keypress before revealing the scratchpad.
local function qconsole_refit()
	local monitor = hl.get_active_monitor()
	if not monitor or not monitor.scale or monitor.scale <= 0 then
		return
	end

	local reserved = monitor.reserved
	local usable = monitor.height / monitor.scale - reserved.top - reserved.bottom
	local bottom = math.max(0, math.floor(usable * 0.5))

	hl.workspace_rule({
		workspace = "special:scratchpad",
		gaps_in = 0,
		gaps_out = { top = 0, right = 0, bottom = bottom, left = 0 },
		no_border = true,
		on_created_empty = "[workspace special:scratchpad silent] omarchy-agent",
	})
end

local function qconsole_toggle()
	qconsole_refit()
	hl.dispatch(hl.dsp.workspace.toggle_special("scratchpad"))
	-- Re-read once Hyprland has committed the workspace visibility change. This
	-- closes the focus-event race that leaves mixed-scale setups using stale
	-- geometry until the pointer moves to another monitor.
	hl.timer(qconsole_refit, { timeout = 50, type = "oneshot" })
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

hl.unbind("SUPER + S") -- Omarchy default: Toggle scratchpad
hl.bind("SUPER + S", qconsole_toggle, { description = "Toggle scratchpad (fit current monitor)" })
o.bind("SUPER + A", "Toggle AI scratchpad", hl.dsp.workspace.toggle_special("AI"))
o.bind("SUPER + D", "Toggle Spotify scratchpad", spotify_toggle)
o.bind("SUPER + SHIFT + M", "Music", spotify_toggle)

o.bind("SUPER + ALT + A", "Move window to AI", hl.dsp.window.move({ workspace = "special:AI", follow = false }))
o.bind("SUPER + ALT + D", "Move window to Spotify", hl.dsp.window.move({ workspace = "special:spotify", follow = false }))

-- ---------------------------------------------------------------------------
-- Dictation
-- ---------------------------------------------------------------------------

o.bind("SUPER + Z", "Toggle dictation", "voxtype record toggle")
o.bind("RETURN", "Stop dictation", "voxtype record stop", { non_consuming = true }) -- re-added after omarchy's region picker tears down; see chezmoi.lua

-- ---------------------------------------------------------------------------
-- System
-- ---------------------------------------------------------------------------

o.bind("SUPER + M", "Show key bindings", "omarchy-menu-keybindings")
o.bind("SUPER + CTRL + ALT + L", "Suspend", "systemctl suspend", { locked = true })
