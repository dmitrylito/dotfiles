---
paths: ["**/.zshrc", "**/.zshenv", "**/.bashrc", "**/.aliases", "**/dot_zshrc*", "**/dot_zshenv*", "**/dot_bashrc*", "**/dot_aliases*"]
---
# Shell config

- Add personal aliases to `~/.aliases` (sourced by `~/.zshrc`; `~/.bashrc` is Omarchy's
  stock file and does not read it).
- These files are chezmoi-managed (`dot_zshrc.tmpl`, `dot_zshenv.tmpl`, `dot_aliases.tmpl`):
  edit the source, not the deployed target.
