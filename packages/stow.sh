#!/bin/bash
set -e

echo "Installing stow..."

if command -v apt-get &>/dev/null; then
    sudo apt-get update
    sudo apt-get install -y stow
elif command -v dnf &>/dev/null; then
    sudo dnf install -y stow
elif command -v pacman &>/dev/null; then
    sudo pacman -Syu --noconfirm stow
elif command -v yum &>/dev/null; then
    sudo yum install -y stow
else
    echo "Could not find a supported package manager (apt-get, dnf, pacman, yum). Please install stow manually."
    exit 1
fi

echo "stow installed successfully."
