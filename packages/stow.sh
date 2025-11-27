#!/bin/bash
set -e

SUDO_CMD=""
if command -v sudo &> /dev/null; then
    SUDO_CMD="sudo"
fi

echo "Installing stow..."

if command -v apt-get &>/dev/null; then
    $SUDO_CMD apt-get update
    $SUDO_CMD apt-get install -y stow
elif command -v dnf &>/dev/null; then
    $SUDO_CMD dnf install -y stow
elif command -v pacman &>/dev/null; then
    $SUDO_CMD pacman -Syu --noconfirm stow
elif command -v yum &>/dev/null; then
    $SUDO_CMD yum install -y stow
else
    echo "Could not find a supported package manager (apt-get, dnf, pacman, yum). Please install stow manually."
    exit 1
fi

echo "stow installed successfully."