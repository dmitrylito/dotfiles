#!/bin/bash
set -e

SUDO_CMD=""
if command -v sudo &> /dev/null; then
    SUDO_CMD="sudo"
fi

echo "Installing zsh..."

if command -v apt-get &>/dev/null; then
    $SUDO_CMD apt-get update
    $SUDO_CMD apt-get install -y zsh
elif command -v dnf &>/dev/null; then
    $SUDO_CMD dnf install -y zsh
elif command -v pacman &>/dev/null; then
    $SUDO_CMD pacman -Syu --noconfirm zsh
elif command -v yum &>/dev/null; then
    $SUDO_CMD yum install -y zsh
else
    echo "Could not find a supported package manager (apt-get, dnf, pacman, yum). Please install zsh manually."
    exit 1
fi

echo "zsh installed successfully."