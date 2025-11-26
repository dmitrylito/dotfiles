#!/bin/bash
set -e

echo "Installing zsh..."

if command -v apt-get &>/dev/null; then
    sudo apt-get update
    sudo apt-get install -y zsh
elif command -v dnf &>/dev/null; then
    sudo dnf install -y zsh
elif command -v pacman &>/dev/null; then
    sudo pacman -Syu --noconfirm zsh
elif command -v yum &>/dev/null; then
    sudo yum install -y zsh
else
    echo "Could not find a supported package manager (apt-get, dnf, pacman, yum). Please install zsh manually."
    exit 1
fi

echo "zsh installed successfully."
