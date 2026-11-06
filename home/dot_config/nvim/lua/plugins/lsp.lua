return {
  {
    "neovim/nvim-lspconfig",
    opts = {
      servers = {
        ruff = {
          keys = {
            {
              "<leader>co",
              function()
                vim.lsp.buf.code_action({
                  apply = true,
                  context = {
                    only = { "source.organizeImports" },
                    diagnostics = {},
                  },
                })
              end,
              desc = "Organize Imports",
            },
          },
        },
        pyright = {
          -- Analyze the whole workspace (not just open files) so project-wide
          -- diagnostics, find-references, and symbol search are complete.
          settings = {
            python = {
              analysis = {
                -- Analyze the whole project on open and build the symbol index
                -- (auto-import + workspace-symbol search), not just open files.
                diagnosticMode = "workspace",
                indexing = true,
                -- Django's dynamic ORM (reverse relations, pk, custom managers)
                -- is unresolvable by pyright; mypy (nvim-lint -> fc-mypy) is the
                -- accurate Django checker. Silence pyright's false positives so
                -- they don't bury real diagnostics across the whole workspace.
                diagnosticSeverityOverrides = {
                  reportAttributeAccessIssue = "none",
                  reportIncompatibleVariableOverride = "none",
                },
              },
            },
          },
          -- Point pyright at a project-local `.venv` when one exists. Without an
          -- interpreter, pyright falls back to the global (mise) Python, which has
          -- no project dependencies installed, so every third-party import (django,
          -- model_utils, ...) is falsely flagged "could not be resolved".
          --
          -- Resolve `.venv` by walking up from the buffer/root rather than trusting
          -- `root_dir`/cwd, which aren't reliably set at before_init time (that
          -- flakiness is what let the errors intermittently return).
          before_init = function(_, config)
            local start = config.root_dir
            if not start or start == "" then
              local fname = vim.api.nvim_buf_get_name(0)
              start = (fname ~= "" and vim.fs.dirname(fname)) or vim.fn.getcwd()
            end
            local venv_root = vim.fs.root(start, ".venv")
            if venv_root then
              local venv_python = venv_root .. "/.venv/bin/python"
              if (vim.uv or vim.loop).fs_stat(venv_python) then
                config.settings = config.settings or {}
                config.settings.python = config.settings.python or {}
                config.settings.python.pythonPath = venv_python
              end
            end
          end,
        },
      },
      setup = {
        copilot = function()
          vim.lsp.inline_completion.enable(true)
        end,
      },
    },
  },
  {
    -- venv-selector still manages VIRTUAL_ENV / PATH / DAP / terminal and the
    -- picker, but must NOT stop+restart the python LSP: pyright's interpreter is
    -- owned deterministically by the before_init hook above. Its default hook
    -- kills a correctly-configured pyright ~1s after startup and races to restart
    -- it, which intermittently leaves pyright on the wrong interpreter. Supplying
    -- a non-empty hooks list suppresses that built-in restart hook.
    "linux-cultist/venv-selector.nvim",
    opts = {
      hooks = {
        function()
          return 1
        end,
      },
    },
  },
}
