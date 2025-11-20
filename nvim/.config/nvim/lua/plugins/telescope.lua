return {
  {
    "nvim-telescope/telescope.nvim",
    defaults = {
      hidden = true,
      find_command = { "fd", "--type", "f", "--color", "never", "--no-require-git", "--follow" },
    },
  },
}
