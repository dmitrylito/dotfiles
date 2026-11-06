require("config.remote_clipboard").setup()
vim.g.mapleader = " "

vim.g.maplocalleader = " "

vim.opt.clipboard = "unnamedplus"

vim.opt.mouse = "a"

vim.opt.mousescroll = "ver:1,hor:1"

vim.opt.conceallevel = 2

vim.opt.spell = false

vim.opt.modeline = true

-- Add hyprlang filetype detection
vim.filetype.add({
  pattern = {
    [".*/hypr/.*%.conf"] = "hyprlang",
  },
})

vim.g.ai_cmp = false

vim.g.root_spec = { { ".git", "lua", "package.json" }, "cwd" }
