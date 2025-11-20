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

# Spaceship prompt
if git clone https://github.com/spaceship-prompt/spaceship-prompt.git \
  "$ZSH_CUSTOM/themes/spaceship-prompt" --depth=1; then
  echo "Cloned spaceship-prompt repo"
else
  echo "Failed to clone spaceship-prompt repo" >&2
  exit 1
fi

ln -s "$ZSH_CUSTOM/themes/spaceship-prompt/spaceship.zsh-theme" \
  "$ZSH_CUSTOM/themes/spaceship.zsh-theme"

# Reload again after installing theme (optional)
source "$HOME"/.zshrc
