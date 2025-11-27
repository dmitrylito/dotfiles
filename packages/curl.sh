#!/bin/bash
set -xe

export DEBIAN_FRONTEND=noninteractive

SUDO_CMD=""
if command -v sudo &> /dev/null; then
    SUDO_CMD="sudo"
fi

if [ -z "$SUDO_CMD" ] && [ "$(id -u)" != "0" ]; then
    echo "This script must be run as root or with sudo."
    exit 1
fi

if command -v curl &>/dev/null; then
    echo "curl is already installed."
    exit 0
fi

echo "Installing curl..."
if command -v apt-get &>/dev/null; then
    $SUDO_CMD apt-get update
    $SUDO_CMD apt-get install -y curl
elif command -v dnf &>/dev/null; then
    $SUDO_CMD dnf install -y curl
elif command -v pacman &>/dev/null; then
    $SUDO_CMD pacman -Syu --noconfirm curl
elif command -v yum &>/dev/null; then
    $SUDO_CMD yum install -y curl
else
    echo "Could not find a supported package manager. Please install curl manually."
    exit 1
fi
