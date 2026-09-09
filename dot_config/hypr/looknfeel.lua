hl.config({
	general = {
		gaps_in = 4,
		gaps_out = 8,
		border_size = 3,
		layout = "dwindle",
		allow_tearing = true,
		snap = {
			enabled = true,
			respect_gaps = true,
		},
	},
	decoration = {
		rounding = 10,
		active_opacity = 1.0,
		inactive_opacity = 1.0,
	},
	scrolling = {
		fullscreen_on_one_column = true,
		column_width = 0.5,
		follow_focus = true,
		focus_fit_method = 1,
		follow_min_visible = 0,
	},
	misc = {
		mouse_move_enables_dpms = false,
	},
})

-- Omarchy's default-opacity windowrule (0.985 0.96) overrides decoration
-- opacity, so the no-transparency preference must be set on the rule too.
o.window({ tag = "default-opacity" }, { opacity = "1 1" })
