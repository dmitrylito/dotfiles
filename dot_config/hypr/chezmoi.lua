-- Personal Hyprland behavior owned by chezmoi.
-- hyprland.lua loads this after Omarchy's defaults, user modules, and toggles.

-- workspaces.lua is generated per device and intentionally not tracked.
local require_optional = require("default.hypr.require_optional")
require_optional.module("hypr.workspaces")

hl.monitor({ output = "", mode = "preferred", position = "auto", scale = 1 })

-- The LG dual-mode panel switches between 4K@144 and 1080p@480 in its own OSD;
-- Hyprland only sees the mode change, so scale and position have to follow it.
-- Positions keep the panel's physical footprint: same centre, same bottom edge,
-- so the pointer still crosses into the Gigabyte below it in either mode.
local lg_dual_mode_description = "LG Electronics LG ULTRAGEAR+ 510RMXX5G570"
local lg_dual_mode_width = nil

-- Keyed by the width Hyprland reports, which is the only signal the OSD switch
-- gives. The 4K side is pinned rather than "preferred" because preferred is
-- 3840x2160@240.08 here; the 1080p EDID is only visible once the panel is in it.
local lg_dual_mode_layout = {
	[3840] = { mode = "3840x2160@144.05", scale = 1.25, position = "0x0" },
	[1920] = { mode = "preferred", scale = 1, position = "480x540" },
}

local function configure_lg_dual_mode()
	for _, monitor in ipairs(hl.get_monitors()) do
		if monitor.description == lg_dual_mode_description then
			local layout = lg_dual_mode_layout[monitor.width]
			if not layout or monitor.width == lg_dual_mode_width then
				return
			end

			lg_dual_mode_width = monitor.width
			hl.monitor({
				output = "desc:" .. lg_dual_mode_description,
				mode = layout.mode,
				position = layout.position,
				scale = layout.scale,
				bitdepth = 10,
			})
			return
		end
	end

	lg_dual_mode_width = nil
end

configure_lg_dual_mode()
hl.on("monitor.added", configure_lg_dual_mode)
hl.on("monitor.layout_changed", configure_lg_dual_mode)

-- Silent, so a launch never flashes the scratchpad over whatever is in front (this
-- is how work-mode starts it). SUPER + D reveals it after a cold launch instead --
-- see spotify_toggle in bindings.lua. Nothing autostarts spotify.
o.window({ class = "^(spotify)$" }, { workspace = "special:spotify silent" })
-- hypr-testbed's nested compositor. Silent, so starting one never lands a window on
-- whatever workspace is in front; `hypr-testbed show` reveals the scratchpad.
o.window({ class = "^(aquamarine)$" }, { workspace = "special:testbed silent" })
o.window({ class = "^(steam)$", title = "^(Counter-Strike 2)$" }, { workspace = "1 silent" })
o.window({ class = "^(cs2)$" }, { fullscreen = true, immediate = true, workspace = "1 silent" })
o.window({ class = "^(gamescope)$" }, { workspace = "1 silent" })

-- Herdr runs inside Ghostty and titles its host window as "hostname: workspace".
-- Keep agent/session updates from activating it over whatever is being used.
o.window({ class = "^(com\\.mitchellh\\.ghostty)$", title = "^.+: .+$" }, { focus_on_activate = false })

-- Omarchy's region picker binds a bare RETURN while its slurp "selection" layer is up,
-- replacing our dictation-stop bind, and its teardown removes only its own handle -- so
-- ours never comes back. Re-add it once the picker is gone (this module loads after
-- omarchy's, so this handler runs after theirs).
local selection_layers = 0

hl.on("layer.opened", function(layer)
	if layer.namespace == "selection" then
		selection_layers = selection_layers + 1
	end
end)

hl.on("layer.closed", function(layer)
	if layer.namespace == "selection" and selection_layers > 0 then
		selection_layers = selection_layers - 1
		if selection_layers == 0 then
			o.bind("RETURN", "Stop dictation", "voxtype record stop", { non_consuming = true })
		end
	end
end)
