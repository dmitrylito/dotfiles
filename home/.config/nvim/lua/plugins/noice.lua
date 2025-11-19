return {
	{
		"folke/noice.nvim",
		event = "VeryLazy",
		lsp = {
			-- override markdown rendering so that **cmp** and other plugins use **Treesitter**
			override = {
				["vim.lsp.util.convert_input_to_markdown_lines"] = true,
				["vim.lsp.util.stylize_markdown"] = true,
				["cmp.entry.get_documentation"] = true, -- requires hrsh7th/nvim-cmp
			},
		},
		opts = {
			views = {
				cmdline_popup = {
					position = {
						row = 45,
						col = "50%",
					},
					size = {
						width = 60,
						height = "auto",
					},
				},
			},
			dependencies = {
				"MunifTanjim/nui.nvim",
				"rcarriga/nvim-notify",
			},
		},
	},
}
