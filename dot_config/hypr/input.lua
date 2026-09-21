hl.config({
	input = {
		kb_layout = "us",
		kb_options = "compose:caps",
		repeat_rate = 40,
		repeat_delay = 600,
		numlock_by_default = true,
		accel_profile = "adaptive",
		follow_mouse = 1,
		sensitivity = 0.4,
		scroll_factor = 1.2,
		natural_scroll = false,
		touchpad = {
			scroll_factor = 0.4,
		},
	},
})

o.window({ class = "(Alacritty|kitty|foot)" }, { scroll_touchpad = 1.5 })
o.window({ class = "com.mitchellh.ghostty" }, { scroll_touchpad = 0.2 })
