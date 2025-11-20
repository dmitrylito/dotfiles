#!/bin/zsh

STOW_DIR="$HOME/dotfiles"
cd "$STOW_DIR" || {
  echo "Failed to change dir to dotfiles at: $STOW_DIR" >&2
  exit 1
}

for pkg in nvim ohmyzsh spaceship zshrc; do
  stow -D "$pkg" && echo "$pkg -D"
done

# Go to home
cd "$HOME"/ || {
  echo "Failed to change dir to home" >&2:
  exit 1
}


# Remove old zsh config
rm -rf "$HOME"/.zshrc && echo "removed zsh files"

# Go to dotfiles
cd "$STOW_DIR" || {
  echo "Failed to change dir to dotfiles" >&2
  exit 1
}

# Stow configs
for pkg in nvim ohmyzsh spaceship zshrc; do
  stow "$pkg" && echo "$pkg -D"
done

# Reload zsh config for current shell (optional, only matters if script is sourced)
source "$HOME"/.zshrc
