-- SUPER+U window pop-out: float the focused window as a centered 16:10 panel and
-- restore it into the dwindle slot it came from.
-- Loaded by hypr/bindings.lua via require("hypr.popout"); returns { toggle }.
--
-- Floating a tiled window deletes its node from the dwindle tree, so restore
-- rebuilds the tree from the saved rectangles rather than by un-floating.
-- swap only permutes windows between existing rectangles; only resize moves a
-- split ratio.
local popout_state = {}
local popout_dir = (os.getenv("XDG_RUNTIME_DIR") or "/tmp") .. "/hypr-popout"
os.execute("mkdir -p " .. popout_dir)

local CUT_TOLERANCE = 2
local SIZE_TOLERANCE = 1
local RESIZE_PASSES = 8

local function popout_file(address)
	return popout_dir .. "/" .. address:gsub("[^%w]", "_")
end

local function popout_coord(vector, key)
	if vector == nil then
		return 0
	end
	return tonumber(vector[key]) or 0
end

local function popout_save(address, state)
	local file = io.open(popout_file(address), "w")
	if file == nil then
		return
	end
	file:write(state.workspace, "\n")
	for _, item in ipairs(state.windows) do
		file:write(item.address, " ", item.x, " ", item.y, " ", item.width, " ", item.height, "\n")
	end
	file:close()
end

local function popout_load(address)
	local file = io.open(popout_file(address), "r")
	if file == nil then
		return nil
	end
	local workspace = tonumber(file:read("*l"))
	local windows = {}
	for line in file:lines() do
		local item, x, y, width, height = line:match("^(%S+) (%S+) (%S+) (%S+) (%S+)$")
		if item ~= nil then
			windows[#windows + 1] = {
				address = item,
				x = tonumber(x),
				y = tonumber(y),
				width = tonumber(width),
				height = tonumber(height),
			}
		end
	end
	file:close()
	if workspace == nil or #windows == 0 then
		return nil
	end
	return { workspace = workspace, windows = windows }
end

local function popout_clear(address)
	popout_state[address] = nil
	os.remove(popout_file(address))
end

local function popout_cut(items, axis)
	local far = axis == "x" and "right" or "bottom"
	local near = axis == "x" and "x" or "y"
	local cuts = {}
	for _, item in ipairs(items) do
		cuts[#cuts + 1] = item[far]
	end
	table.sort(cuts)

	for _, cut in ipairs(cuts) do
		local low, high = {}, {}
		local clean = true
		for _, item in ipairs(items) do
			if item[far] <= cut + CUT_TOLERANCE then
				low[#low + 1] = item
			elseif item[near] >= cut - CUT_TOLERANCE then
				high[#high + 1] = item
			else
				clean = false
				break
			end
		end
		if clean and #low > 0 and #high > 0 then
			return low, high
		end
	end

	return nil
end

local function popout_tree(items)
	if #items == 1 then
		return { address = items[1].address }
	end

	local orientation = "v"
	local low, high = popout_cut(items, "x")
	if low == nil then
		orientation = "h"
		low, high = popout_cut(items, "y")
	end
	if low == nil then
		return nil
	end

	local left = popout_tree(low)
	local right = popout_tree(high)
	if left == nil or right == nil then
		return nil
	end
	return { orientation = orientation, left = left, right = right }
end

local function popout_leader(node)
	while node.address == nil do
		node = node.left
	end
	return node.address
end

-- Visiting a node before its children keeps every anchor a leaf when it is used.
local function popout_steps(node, steps)
	if node.address ~= nil then
		return steps
	end
	steps[#steps + 1] = {
		anchor = popout_leader(node.left),
		window = popout_leader(node.right),
		orientation = node.orientation,
	}
	popout_steps(node.left, steps)
	popout_steps(node.right, steps)
	return steps
end

local function popout_retile(state, tree)
	for _, item in ipairs(state.windows) do
		local window = hl.get_window("address:" .. item.address)
		if window ~= nil and not window.floating then
			hl.dispatch(hl.dsp.window.float({ action = "toggle", window = "address:" .. item.address }))
		end
	end

	hl.dispatch(hl.dsp.window.float({ action = "toggle", window = "address:" .. popout_leader(tree) }))

	for _, step in ipairs(popout_steps(tree, {})) do
		hl.dispatch(hl.dsp.focus({ window = "address:" .. step.anchor }))
		hl.dispatch(hl.dsp.window.float({ action = "toggle", window = "address:" .. step.window }))

		local anchor = hl.get_window("address:" .. step.anchor)
		local placed = hl.get_window("address:" .. step.window)
		if anchor ~= nil and placed ~= nil then
			local dx = math.abs(popout_coord(anchor.at, "x") - popout_coord(placed.at, "x"))
			local dy = math.abs(popout_coord(anchor.at, "y") - popout_coord(placed.at, "y"))
			if (dx > dy) ~= (step.orientation == "v") then
				hl.dispatch(hl.dsp.focus({ window = "address:" .. step.window }))
				hl.dispatch(hl.dsp.layout("togglesplit"))
			end
		end
	end
end

-- resize is exact on a left/top child and lands on 2*current-target on a
-- right/bottom one, so a missed target is simply re-asked for mirrored.
local function popout_set_axis(address, key, target)
	local window = hl.get_window("address:" .. address)
	if window == nil then
		return
	end
	local other = key == "x" and "y" or "x"

	local function ask(value)
		local current = hl.get_window("address:" .. address)
		if current == nil then
			return
		end
		-- The mirrored retry can overshoot past zero, and resize rejects a
		-- non-positive extent with an "Invalid size" error overlay.
		local wanted = math.floor(value)
		local keep = math.floor(popout_coord(current.size, other))
		if wanted < 1 or keep < 1 then
			return
		end
		local args = { relative = false }
		args[key] = wanted
		args[other] = keep
		hl.dispatch(hl.dsp.focus({ window = "address:" .. address }))
		hl.dispatch(hl.dsp.window.resize(args))
	end

	ask(target)
	local landed = hl.get_window("address:" .. address)
	if landed ~= nil and math.abs(popout_coord(landed.size, key) - target) > SIZE_TOLERANCE then
		ask(2 * popout_coord(landed.size, key) - target)
	end
end

local function popout_apply_sizes(state)
	for _ = 1, RESIZE_PASSES do
		local worst = 0
		for _, item in ipairs(state.windows) do
			local window = hl.get_window("address:" .. item.address)
			if window ~= nil and not window.floating then
				local dw = math.abs(popout_coord(window.size, "x") - item.width)
				local dh = math.abs(popout_coord(window.size, "y") - item.height)
				worst = math.max(worst, dw, dh)
				if dw > SIZE_TOLERANCE then
					popout_set_axis(item.address, "x", item.width)
				end
				if dh > SIZE_TOLERANCE then
					popout_set_axis(item.address, "y", item.height)
				end
			end
		end
		if worst <= SIZE_TOLERANCE then
			break
		end
	end
end

local function popout_panel_size(monitor)
	local width = monitor.width / monitor.scale
	local height = monitor.height / monitor.scale
	local pop_width = width * 0.80
	local pop_height = pop_width / 1.6
	if pop_height > height * 0.82 then
		pop_height = height * 0.82
		pop_width = pop_height * 1.6
	end
	return math.floor(pop_width), math.floor(pop_height)
end

local function popout_float(window)
	local monitor = hl.get_active_monitor()
	if monitor == nil then
		return
	end

	local snapshot = {}
	for _, candidate in ipairs(hl.get_workspace_windows(window.workspace.id)) do
		if not candidate.floating then
			snapshot[#snapshot + 1] = {
				address = candidate.address,
				x = popout_coord(candidate.at, "x"),
				y = popout_coord(candidate.at, "y"),
				width = popout_coord(candidate.size, "x"),
				height = popout_coord(candidate.size, "y"),
			}
		end
	end
	if #snapshot == 0 then
		return
	end

	local state = { workspace = window.workspace.id, windows = snapshot }
	popout_state[window.address] = state
	popout_save(window.address, state)

	local pop_width, pop_height = popout_panel_size(monitor)

	hl.dispatch(hl.dsp.window.float({ action = "toggle" }))
	hl.dispatch(hl.dsp.window.resize({
		x = pop_width,
		y = pop_height,
		relative = false,
	}))
	hl.dispatch(hl.dsp.window.center())
end

local function popout_restore(window, state)
	local address = window.address

	-- Every saved window must still be here and tiled (bar the popped one), or
	-- the recorded rectangles no longer describe a layout worth rebuilding.
	local present = 0
	for _, item in ipairs(state.windows) do
		local candidate = hl.get_window("address:" .. item.address)
		if candidate == nil then
			break
		end
		if item.address == address or not candidate.floating then
			present = present + 1
		end
	end

	local tiled = 0
	for _, candidate in ipairs(hl.get_workspace_windows(state.workspace)) do
		if not candidate.floating then
			tiled = tiled + 1
		end
	end

	local items = {}
	for _, item in ipairs(state.windows) do
		items[#items + 1] = {
			address = item.address,
			x = item.x,
			y = item.y,
			right = item.x + item.width,
			bottom = item.y + item.height,
		}
	end
	local tree = popout_tree(items)

	if tree == nil or present ~= #state.windows or tiled + 1 ~= #state.windows then
		hl.dispatch(hl.dsp.window.float({ action = "toggle" }))
		popout_clear(address)
		return
	end

	popout_retile(state, tree)
	popout_apply_sizes(state)
	hl.dispatch(hl.dsp.focus({ window = "address:" .. address }))
	popout_clear(address)
end

local function popout_toggle()
	local window = hl.get_active_window()
	if window == nil then
		return
	end

	if not window.floating then
		popout_float(window)
		return
	end

	local state = popout_state[window.address] or popout_load(window.address)
	if state == nil then
		hl.dispatch(hl.dsp.window.float({ action = "toggle" }))
		return
	end
	popout_restore(window, state)
end

return { toggle = popout_toggle, panel_size = popout_panel_size }
