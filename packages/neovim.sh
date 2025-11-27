#!/bin/bash
set -xe

# sh ./fonts.sh

NVIM_VERSION=v0.10.0

SUDO_CMD=""
if command -v sudo &> /dev/null; then
    SUDO_CMD="sudo"
fi

if [ -z "$SUDO_CMD" ] && [ "$(id -u)" != "0" ]; then
    echo "This script must be run as root or with sudo."
    exit 1
fi

# Installing neovim dependencies
echo "Installing Neovim dependencies..."
if command -v apt-get &>/dev/null; then
    $SUDO_CMD apt-get update
    $SUDO_CMD apt-get install -y git curl zip libluajit-5.1-dev ripgrep fd-find
elif command -v dnf &>/dev/null; then
    $SUDO_CMD dnf install -y git curl zip luajit-devel ripgrep fd-find
elif command -v pacman &>/dev/null; then
    $SUDO_CMD pacman -Syu --noconfirm git curl zip luajit ripgrep fd
elif command -v yum &>/dev/null; then
    $SUDO_CMD yum install -y git curl zip luajit-devel ripgrep fd-find
else
    echo "Could not find a supported package manager. Please install dependencies manually."
    exit 1
fi

# Installing lazy git
if ! command -v lazygit &>/dev/null; then
    echo "Installing lazygit..."
    TEMP_DIR_LAZYGIT=$(mktemp -d)
    
    LAZYGIT_VERSION=$(curl -s "https://api.github.com/repos/jesseduffield/lazygit/releases/latest" | grep -Po '"tag_name": "v\K[^"]*')
    curl -Lo "${TEMP_DIR_LAZYGIT}/lazygit.tar.gz" "https://github.com/jesseduffield/lazygit/releases/latest/download/lazygit_${LAZYGIT_VERSION}_Linux_x86_64.tar.gz"
    tar -C "${TEMP_DIR_LAZYGIT}" -xf "${TEMP_DIR_LAZYGIT}/lazygit.tar.gz" lazygit
    $SUDO_CMD install "${TEMP_DIR_LAZYGIT}/lazygit" /usr/local/bin
    rm -rf "${TEMP_DIR_LAZYGIT}"
else
    echo "lazygit is already installed."
fi


# Install Neovim
NEOVIM_INSTALLED_VERSION=""
if command -v nvim &>/dev/null; then
    NEOVIM_INSTALLED_VERSION=$(nvim --version | head -n 1 | sed 's/NVIM //')
fi

if [[ "$NEOVIM_INSTALLED_VERSION" == "$NVIM_VERSION" ]]; then
    echo "Neovim ${NVIM_VERSION} is already installed."
else
    if [ -n "$NEOVIM_INSTALLED_VERSION" ]; then
        echo "Found Neovim ${NEOVIM_INSTALLED_VERSION}, upgrading to ${NVIM_VERSION}."
    else
        echo "Installing Neovim ${NVIM_VERSION}..."
    fi

    DOWNLOAD_URL="https://github.com/neovim/neovim/releases/download/${NVIM_VERSION}/nvim-linux64.tar.gz"
    
    TEMP_DIR_NVIM=$(mktemp -d)
    
    curl -L -o "${TEMP_DIR_NVIM}/nvim-linux64.tar.gz" "$DOWNLOAD_URL"
    tar -C "${TEMP_DIR_NVIM}" -xzf "${TEMP_DIR_NVIM}/nvim-linux64.tar.gz"
    
    # Overwrite existing files in /usr/local
    $SUDO_CMD cp -r "${TEMP_DIR_NVIM}/nvim-linux64/"* /usr/local/
    
    rm -rf "${TEMP_DIR_NVIM}"
    
    echo "Neovim ${NVIM_VERSION} installed successfully."
fi
