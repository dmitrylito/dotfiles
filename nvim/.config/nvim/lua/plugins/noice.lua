return {
  "folke/noice.nvim",
  opts = {
    views = {
      cmdline_popup = {
        position = {
          row = "75%",
          col = "50%",
        },
        size = {
          width = 60,
          height = "auto",
        },
        border = {
          style = "rounded",
          padding = { 0, 3 },
        },
        win_options = {
          winhighlight = { Normal = "NormalFloat", FloatBorder = "NoiceCmdlinePopupBorder" },
        },
      },
    },
  },
  config = function(_, opts)
    require("noice").setup(opts)

    -- fix the background
    vim.api.nvim_set_hl(0, "NoiceCmdlinePopup", { link = "NormalFloat" })
    vim.api.nvim_set_hl(0, "NoiceCmdlinePopupBorder", { link = "FloatBorder" })
  end,
}
