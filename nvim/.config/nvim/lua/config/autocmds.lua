-- Autocmds are automatically loaded on the VeryLazy event
-- Default autocmds that are always set: https://github.com/LazyVim/LazyVim/blob/main/lua/lazyvim/config/autocmds.lua
--
-- Add any additional autocmds here
-- with `vim.api.nvim_create_autocmd`
--
-- Or remove existing autocmds by their group name (which is prefixed with `lazyvim_` for the defaults)
-- e.g. vim.api.nvim_del_augroup_by_name("lazyvim_wrap_spell")
-- Auto-open Snacks dashboard when the last normal buffer is closed
vim.api.nvim_create_autocmd("BufDelete", {
	group = vim.api.nvim_create_augroup("SnacksDashboardOnEmpty", { clear = true }),
	callback = function()
		-- Check the number of non-nofile buffers
		local actual_buffers = {}
		for _, buf in ipairs(vim.api.nvim_list_bufs()) do
			if vim.bo[buf].buftype ~= "nofile" then
				table.insert(actual_buffers, buf)
			end
		end

		-- Open the Snacks dashboard if the current buffer is the last actual one
		if #actual_buffers == 1 and vim.api.nvim_buf_get_name(actual_buffers[1]) == "" then
			vim.cmd("SnacksDashboard")
		end
	end,
})
