-- Omarchy's Quake console (default/hypr/qconsole.lua) with our seed, laid out
-- in quarters of the monitor and capped at four windows.
--
-- Its height share and seed command are locals, and its event handlers are
-- registered before any user module loads, so a second module refitting the same
-- workspace rule ends up fighting it: whichever handler ran last sets the height,
-- which is the console resizing itself at random. hyprland.lua stops Omarchy
-- from loading its copy (see modify_hyprland.lua) and this loads that same file
-- with the seed, height and layout patched in, so upstream fixes still arrive
-- with updates.
-- The layout goes into Omarchy's own rule because every refit replaces that rule.

local upstream = (os.getenv("OMARCHY_PATH") or "/usr/share/omarchy") .. "/default/hypr/qconsole.lua"

local CONSOLE = "special:qconsole"
local LIMIT = 4

local patches = {
	{
		'local seed = "[workspace " .. CONSOLE .. " silent] omarchy-agent"',
		'local seed = "[workspace " .. CONSOLE .. " silent] herdr-agent"',
	},
	-- The top half holds two windows; a third needs the bottom half too.
	{ "local share = 0.5", "local share = 0.5\nlocal share_for = ..." },
	{ "local tall = math.floor(height * share)", "local tall = math.floor(height * (share_for and share_for(share) or share))" },
	{
		"    on_created_empty = seed,",
		'    on_created_empty = seed,\n    layout = "lua:qconsole-quarters",',
	},
}

-- Arrival order, so a window keeps its quarter while others open and close.
local order = {}

local function target_key(target)
	local window = target.window
	return window and tostring(window.stable_id) or ("target" .. target.index)
end

local function tiled_on_console()
	local count = 0
	for _, window in ipairs(hl.get_workspace_windows(CONSOLE)) do
		if not window.floating then
			count = count + 1
		end
	end
	return count
end

local function share_for(share)
	return tiled_on_console() > 2 and 1 or share
end

-- 1: whole console. 2: left | right. 3 and 4: quarters, filled top left, top
-- right, bottom left, bottom right; the console is then the full monitor height.
local function quarters(ctx, n)
	local left, right = ctx:split(ctx.area, "left", 0.5), ctx:split(ctx.area, "right", 0.5)
	if n == 1 then
		return { ctx.area }
	end
	if n == 2 then
		return { left, right }
	end
	return {
		ctx:split(left, "top", 0.5),
		ctx:split(right, "top", 0.5),
		ctx:split(left, "bottom", 0.5),
		ctx:split(right, "bottom", 0.5),
	}
end

hl.layout.register("qconsole-quarters", {
	recalculate = function(ctx)
		local targets, present = {}, {}
		for _, target in ipairs(ctx.targets) do
			local key = target_key(target)
			targets[key] = target
			present[key] = true
		end

		local kept = {}
		for _, key in ipairs(order) do
			if present[key] then
				table.insert(kept, key)
				present[key] = nil
			end
		end
		for _, target in ipairs(ctx.targets) do
			if present[target_key(target)] then
				table.insert(kept, target_key(target))
			end
		end
		order = kept

		if #order == 0 then
			return
		end

		-- A fifth window sits on the last quarter until evict() moves it out.
		local cells = quarters(ctx, math.min(#order, LIMIT))
		for i, key in ipairs(order) do
			targets[key]:place(cells[math.min(i, LIMIT)])
		end
	end,
})

local file = assert(io.open(upstream, "r"))
local source = file:read("a")
file:close()

local missing = {}
for _, patch in ipairs(patches) do
	local from, to = patch[1], patch[2]
	local at = source:find(from, 1, true)
	if at then
		source = source:sub(1, at - 1) .. to .. source:sub(at + #from)
	else
		table.insert(missing, from)
	end
end

assert(load(source, "@" .. upstream))(share_for)

-- Omarchy's console still works unpatched, just at its own size, so report the
-- drift instead of failing the whole config.
if #missing > 0 then
	hl.exec_cmd(
		"notify-send -u critical 'hypr/qconsole.lua' 'Omarchy qconsole.lua changed; scratchpad uses upstream defaults'"
	)
end

-- Floating windows (dialogs, pickers) are not laid out in quarters, so only tiled
-- ones count toward the cap.
local function evict(window)
	if not window or window.floating or not window.workspace or window.workspace.name ~= CONSOLE then
		return
	end
	if tiled_on_console() <= LIMIT then
		return
	end
	local workspace = hl.get_active_workspace()
	if not workspace then
		return
	end
	hl.dispatch(hl.dsp.window.move({ workspace = tostring(workspace.id), window = window, follow = false }))
	hl.exec_cmd("notify-send 'Quake console' 'Full at " .. LIMIT .. " windows; opened on the workspace below'")
end

hl.on("window.open", evict)
hl.on("window.move_to_workspace", evict)
