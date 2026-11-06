-- No diagnostics in markdown buffers; other buffers keep theirs
vim.api.nvim_create_autocmd("FileType", {
  pattern = "markdown",
  callback = function(args)
    vim.diagnostic.enable(false, { bufnr = args.buf })
  end,
})

-- Enable mouse scrolling in terminal mode
vim.api.nvim_create_autocmd("TermOpen", {
  group = vim.api.nvim_create_augroup("terminal_scroll", { clear = true }),
  callback = function(args)
    local ft = vim.bo[args.buf].filetype
    if ft == "snacks_terminal" then
      return
    end
    vim.keymap.set("t", "<ScrollWheelUp>", [[<C-\><C-o><ScrollWheelUp>]], { buffer = args.buf, silent = true })
    vim.keymap.set("t", "<ScrollWheelDown>", [[<C-\><C-o><ScrollWheelDown>]], { buffer = args.buf, silent = true })
  end,
})
