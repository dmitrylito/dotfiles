return {
  "ibhagwan/fzf-lua",
  opts = {
    fzf_opts = {
      ["--layout"] = "default",
    },
    winopts = {
      width = 0.95,
      height = 0.95,

      preview = {
        layout = "horizontal",
        wrap = "wrap",
        horizontal = "right:50%",
      },
    },
    files = {
      hidden = true,
      follow = true,
    },
  },
}
