return {
	{
		"folke/snacks.nvim",
		opts = {
			dashboard = {
				show_recent_files = true,
			},
			explorer = {},

			picker = {
				layouts = {
					default = {
						reverse = true,
						layout = {
							box = "horizontal",
							width = 0.95,
							height = 0.95,

							{
								box = "vertical",
								border = "rounded",
								title = "{title} {live} {flags}",

								{ win = "list", border = "none" },
								{ win = "input", height = 1, border = "top" },
							},

							{
								win = "preview",
								title = "{preview}",
								border = "rounded",
								width = 0.65,
							},
						},
					},
				},
				sources = {
					files = {
						follow = true,
						hidden = true,
						ignored = true,
					},
					explorer = {
						hidden = true,
						follow = true,
					},
				},
			},
		},
	},
}
