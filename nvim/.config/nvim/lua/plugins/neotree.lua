return {
	{
		"nvim-neo-tree/neo-tree.nvim",
		branch = "v3.x",
		dependencies = {
			"nvim-lua/plenary.nvim",
			"MunifTanjim/nui.nvim",
		},
		config = function()
			require("neo-tree").setup({
				window = {
					position = "left",
					width = 30,
				},
				filesystem = {
					filtered_items = {
						hide_dotfiles = false,
						hide_git_ignored = true,
					},
				},
			})
		end,
	},
}
