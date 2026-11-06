return {
  --Adds a line in nvim, makes it skiny

  {
    "xiyaowong/virtcolumn.nvim",
  },

  -- Center the cursor vertically when navigating

  {
    "arnamak/stay-centered.nvim",
    opts = {
      enable = true,
      cursorline = true,
      disable_on_mouse = true,
      skip_filetypes = { "sidekick_terminal", "snacks_terminal" },
    },
  },

  {
    "saghen/blink.cmp",
    opts = function(_, opts)
      opts.keymap = opts.keymap or {}
      opts.keymap.preset = "enter"
      opts.keymap["<Tab>"] = {
        function(cmp)
          if vim.lsp.inline_completion and vim.lsp.inline_completion.get() then
            return true
          end
        end,
        "fallback",
      }
    end,
  },

  {
    "stevearc/conform.nvim",
    opts = {
      formatters_by_ft = {
        zsh = { "shfmt" },
      },
    },
  },

  { "folke/lazy.nvim", version = false },

  {
    "LazyVim/LazyVim",
    version = false,
    opts = {
      news = {
        lazyvim = false,
        neovim = false,
      },
    },
  },

  {
    "MagicDuck/grug-far.nvim",
    config = function()
      require("grug-far").setup({})
    end,
  },

  {
    "folke/sidekick.nvim",
    opts = {
      cli = {
        win = {
          config = function(terminal) end,
        },
      },
    },
  },

  {
    "MeanderingProgrammer/render-markdown.nvim",
    opts = {
      latex = { enabled = false },
    },
  },

  {
    "folke/noice.nvim",
    opts = {
      views = {
        cmdline_popup = {
          position = {
            row = "40%",
            col = "50%",
          },
        },
      },
    },
  },
}
