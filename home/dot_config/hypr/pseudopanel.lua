-- SUPER+P pseudo panel: pseudotile the focused window at the same centered 16:10
-- size SUPER+U pops out to, and stand aside while it shares the workspace.
-- Loaded by hypr/bindings.lua via require("hypr.pseudopanel"); returns { toggle }.
--
-- Unlike the pop-out this keeps the window in the dwindle tree, so a second
-- window tiles against it normally and closing that one brings the panel back
-- with no saved layout to rebuild. Hyprland keeps a window's pseudo size across
-- a pseudo off/on, so the size is only ever asked for once.

local popout = require("hypr.popout")

-- Exact resize lands reliably on a pseudotiled window that owns the whole
-- workspace, but not on a child of a split (hyprwm/Hyprland#8562, closed as not
-- planned), where the tile also clamps the result. So sizing waits for the
-- window to be alone; `sized` records that it no longer has to.
local marked = {}
local active = {}
local sized = {}

-- window.close fires before the tree has dropped the node, so the counts are
-- only right a beat later.
local RECONCILE_DELAY = 60

local function tiled_count(workspace)
	local count = 0
	for _, candidate in ipairs(hl.get_workspace_windows(workspace)) do
		if not candidate.floating then
			count = count + 1
		end
	end
	return count
end

local function pseudo_toggle(address)
	hl.dispatch(hl.dsp.window.pseudo({ window = "address:" .. address }))
end

local function apply_panel_size(address)
	local monitor = hl.get_active_monitor()
	if monitor == nil then
		return
	end
	local width, height = popout.panel_size(monitor)
	hl.dispatch(hl.dsp.focus({ window = "address:" .. address }))
	hl.dispatch(hl.dsp.window.resize({ x = width, y = height, relative = false }))
	sized[address] = true
end

local function forget(address)
	marked[address] = nil
	active[address] = nil
	sized[address] = nil
end

local function reconcile()
	for address in pairs(marked) do
		local window = hl.get_window("address:" .. address)
		if window == nil then
			forget(address)
		elseif not window.floating and window.workspace ~= nil then
			local alone = tiled_count(window.workspace.id) == 1
			if alone and not active[address] then
				pseudo_toggle(address)
				active[address] = true
				if not sized[address] and window.active then
					apply_panel_size(address)
				end
			elseif not alone and active[address] then
				pseudo_toggle(address)
				active[address] = nil
			end
		end
	end
end

local function reconcile_soon()
	hl.timer(reconcile, { timeout = RECONCILE_DELAY, type = "oneshot" })
end

local function toggle()
	local window = hl.get_active_window()
	if window == nil or window.workspace == nil then
		return
	end
	local address = window.address

	if marked[address] then
		if active[address] then
			pseudo_toggle(address)
		end
		forget(address)
		return
	end

	marked[address] = true
	if window.floating or tiled_count(window.workspace.id) ~= 1 then
		return
	end

	pseudo_toggle(address)
	active[address] = true
	apply_panel_size(address)
end

for _, event in ipairs({ "window.open", "window.close", "window.destroy", "window.move_to_workspace" }) do
	hl.on(event, reconcile_soon)
end

return { toggle = toggle }
