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

# Make sure ZSH_CUSTOM is set consistently
ZSH_CUSTOM="${ZSH_CUSTOM:-$HOME/.oh-my-zsh-custom/custom}"
THEME_LINK="$ZSH_CUSTOM/themes/spaceship.zsh-theme"
THEME_TARGET="$ZSH_CUSTOM/themes/spaceship-prompt/spaceship.zsh-theme"

# Remove Spaceship files (only if they actually exist)
if [ -d "$ZSH_CUSTOM/themes/spaceship-prompt" ]; then
  echo "Removing existing spaceship-prompt directory at $ZSH_CUSTOM/themes/spaceship-prompt"
  if ! rm -rf "$ZSH_CUSTOM/themes/spaceship-prompt"; then
    echo "Failed to remove spaceship-prompt directory" >&2
    exit 1
  fi
fi

if [ -e "$ZSH_CUSTOM/themes/spaceship.zsh-theme" ]; then
  echo "Removing existing spaceship.zsh-theme at $ZSH_CUSTOM/themes/spaceship.zsh-theme"
  if ! rm -f "$ZSH_CUSTOM/themes/spaceship.zsh-theme"; then
    echo "Failed to remove spaceship.zsh-theme" >&2
    exit 1
  fi
fi

echo "Spaceship files removed (or were not present)"

# Spaceship prompt
if git clone https://github.com/spaceship-prompt/spaceship-prompt.git \
  "$ZSH_CUSTOM/themes/spaceship-prompt" --depth=1; then
  echo "Cloned spaceship-prompt repo"
else
  echo "Failed to clone spaceship-prompt repo" >&2
  exit 1
fi

if [ -L "$THEME_LINK" ]; then
  current_target="$(readlink "$THEME_LINK")"
  if [ "$current_target" = "$THEME_TARGET" ]; then
    echo "Symlink already correct: $THEME_LINK -> $current_target"
  else
    echo "Symlink $THEME_LINK points to $current_target, replacing with $THEME_TARGET"
    rm "$THEME_LINK" || { echo "Failed to remove existing symlink $THEME_LINK" >&2; exit 1; }
    ln -s "$THEME_TARGET" "$THEME_LINK" || { echo "Failed to create symlink $THEME_LINK" >&2; exit 1; }
  fi
elif [ -e "$THEME_LINK" ]; then
  echo "$THEME_LINK exists and is not a symlink, refusing to overwrite blindly" >&2
  exit 1
else
  ln -s "$THEME_TARGET" "$THEME_LINK" || { echo "Failed to create symlink $THEME_LINK" >&2; exit 1; }
  echo "Created spaceship.zsh-theme symlink: $THEME_LINK -> $THEME_TARGET"
fi

# Reload again after installing theme (optional)
source "$HOME"/.zshrc
