return {
  {
    "mfussenegger/nvim-lint",
    ft = { "python" },
    config = function()
      local lint = require("lint")

      -- Route mypy through fc-dmypy: the mypy DAEMON (fast, ~sub-second warm)
      -- with the django-stubs plugin, so Django's dynamic ORM (reverse relations,
      -- pk, custom managers) resolves — which pyright cannot do. The wrapper loads
      -- docker/envs so django.setup() works on the host and filters output to the
      -- current file. Output format flags live in ~/.config/fleetchaser-mypy.ini,
      -- so no CLI args are passed.
      -- fc-dmypy only deploys to work machines; elsewhere Python gets no mypy linter.
      local fc_dmypy = vim.fn.expand("~/.local/bin/fc-dmypy")
      if vim.fn.executable(fc_dmypy) == 1 then
        lint.linters.mypy.cmd = fc_dmypy
        lint.linters.mypy.args = {}
        lint.linters_by_ft = { python = { "mypy" } }
      end

      local grp = vim.api.nvim_create_augroup("fc_nvim_lint", { clear = true })
      vim.api.nvim_create_autocmd({ "BufWritePost", "BufReadPost" }, {
        group = grp,
        pattern = "*.py",
        callback = function()
          require("lint").try_lint()
        end,
      })

      -- Lint the buffer that triggered plugin load (its BufReadPost already fired).
      if vim.bo.filetype == "python" then
        lint.try_lint()
      end
    end,
  },
}
