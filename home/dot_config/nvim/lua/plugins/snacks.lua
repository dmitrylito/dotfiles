return {
  "folke/snacks.nvim",
  priority = 1000,
  lazy = false,
  opts = {
    bigfile = { enabled = true },
    explorer = { enabled = true },
    indent = { enabled = true },
    input = { enabled = true },
    notifier = { enabled = true },
    quickfile = { enabled = true },
    scope = { enabled = true },
    scroll = { enabled = false },
    statuscolumn = { enabled = true },
    words = { enabled = true },
    image = { enabled = true },
    dashboard = { enabled = true },

    picker = {
      sources = {
        explorer = {
          cycle = true,
          auto_close = true,
          layout = { preview = "main" },
          follow = true,
          hidden = true,
          ignored = true,
          exclude = {
            ".git",
            "node_modules",
            "vendor",
            "**/__pycache__",
            "**/.DS_Store",
            "**/.ruff_cache",
            "**/.venv",
          },
        },
        files = {
          follow = true,
          hidden = true,
          ignored = false,
        },
        grep = {
          follow = true,
          hidden = true,
          ignored = false,
        },
      },

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
    },
  },
}
