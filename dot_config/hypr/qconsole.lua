-- Omarchy's scratchpad console (default/hypr/qconsole.lua) with our seed.
--
-- Its height share and seed command are locals, and its event handlers are
-- registered before any user module loads, so a second module refitting the same
-- workspace rule ends up fighting it: whichever handler ran last sets the height,
-- which is the console resizing itself at random. hyprland.lua stops Omarchy
-- from loading its copy (see modify_hyprland.lua) and this loads that same file
-- with the seed swapped, so upstream fixes still arrive with updates.

local upstream = (os.getenv("OMARCHY_PATH") or "/usr/share/omarchy") .. "/default/hypr/qconsole.lua"

local patches = {
	{
		'local seed = "[workspace special:scratchpad silent] omarchy-agent"',
		'local seed = "[workspace special:scratchpad silent] herdr-agent"',
	},
}

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

assert(load(source, "@" .. upstream))()

-- Omarchy's console still works unpatched, just at its own size, so report the
-- drift instead of failing the whole config.
if #missing > 0 then
	hl.exec_cmd(
		"notify-send -u critical 'hypr/qconsole.lua' 'Omarchy qconsole.lua changed; scratchpad uses upstream defaults'"
	)
end
