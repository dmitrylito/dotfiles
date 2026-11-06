return {
  {
    "folke/tokyonight.nvim",
    style = "night",
    opts = {
      transparent = true,
      styles = {
        sidebars = "transparent",
        floats = "transparent",
        functions = {},
      },
      -- disable italic for functions
      auto_integrations = true,
      on_colors = function(colors)
        colors.hint = colors.orange
        colors.error = "#ff0000"
      end,
    },
  },
  {
    "LazyVim/LazyVim",
    opts = {
      colorscheme = "catppuccin",
    },
  },
  {
    "catppuccin/nvim",
    name = "catppuccin",
    priority = 1000,
    opts = {
      flavour = "mocha", -- latte, frappe, macchiato, mocha
      transparent_background = true, -- disables setting the background color.
      float = {
        transparent = true, -- enable transparent floating windows
        solid = true, -- use solid styling for floating windows, see |winborder|
      },
      integrations = {
        -- For more plugins integrations please scroll down (
        "folke/snacks.nvim",
        "kdheepack/lazygit.nvim",
      },
      auto_integrations = false,
      on_colors = function(colors)
        colors.hint = colors.orange
        colors.error = "#ff0000"
      end,
    },
  },
}
