#!/bin/bash
set -e

# Sudo check
SUDO_CMD=""
if command -v sudo &> /dev/null; then
    SUDO_CMD="sudo"
fi

if command -v nvim &> /dev/null; then
    echo "Neovim is already installed."
    exit 0
fi

echo "Installing latest Neovim..."

# Get download URL for latest nvim-linux64.tar.gz
DOWNLOAD_URL=$(curl -s https://api.github.com/repos/neovim/neovim/releases/latest | grep "browser_download_url.*nvim-linux64.tar.gz" | cut -d '"' -f 4)

if [ -z "$DOWNLOAD_URL" ]; then
    echo "Could not find download URL for Neovim."
    exit 1
fi

# Download
TEMP_DIR=$(mktemp -d)
cd "$TEMP_DIR"
echo "Downloading Neovim from $DOWNLOAD_URL"
curl -L -o nvim-linux64.tar.gz "$DOWNLOAD_URL"

# Extract
tar xzf nvim-linux64.tar.gz

# Install
# The extracted directory is nvim-linux64
if [ -n "$SUDO_CMD" ]; then
    $SUDO_CMD cp -r nvim-linux64/* /usr/local/
else
    cp -r nvim-linux64/* /usr/local/
fi


# Cleanup
cd - > /dev/null
rm -rf "$TEMP_DIR"

echo "Neovim installed successfully."
