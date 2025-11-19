return {
  {
    "nvim-neo-tree/neo-tree.nvim",
    branch = "v3.x",
    dependencies = {
      "nvim-lua/plenary.nvim",
      "nvim-tree/nvim-web-devicons", -- Recommended for icons
      "MunifTanjim/nui.nvim",
      -- "3rd/image.nvim", -- Optional: for image support in preview
    },
    config = function()
      require("neo-tree").setup({
        -- Your Neo-tree configuration options here
        -- For example:
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
