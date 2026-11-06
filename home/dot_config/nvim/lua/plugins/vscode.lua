--return {}
if not vim.g.vscode then
    return {}
end

return {
    {
        "folke/snacks.nvim",
        opts = {
            bigfile = { enabled = false },
            dashboard = { enabled = false },
            explorer = { enabled = false },
            indent = { enabled = false },
            input = { enabled = false },
            picker = { enabled = false },
            notifier = { enabled = false },
            quickfile = { enabled = false },
            scope = { enabled = false },
            scroll = { enabled = false },
            statuscolumn = { enabled = false },
            words = { enabled = false },
        },
    },
    { "folke/noice.nvim", enabled = false },
    { "nvim-lualine/lualine.nvim", enabled = false },
    { "rcarriga/nvim-notify", enabled = false },
    { "akinsho/bufferline.nvim", enabled = false },
    { "lukas-reineke/indent-blankline.nvim", enabled = false },
    { "lewis6991/gitsigns.nvim", enabled = false },
    { "rrethy/vim-illuminate", enabled = false },
}
