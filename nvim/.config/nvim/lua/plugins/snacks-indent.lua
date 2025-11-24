return {
	"folke/snacks.nvim",
	opts = {
		indent = {
			enabled = true, -- turn Snacks indent on
			only_scope = false, -- set to true if you ONLY want the scope line
			scope = {
				enabled = true, -- <- this is the important part
				only_current = true, -- highlight only the block under cursor
			},
		},
	},
}
