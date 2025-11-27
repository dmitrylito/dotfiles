#!/bin/bash
set -e

SUDO_CMD=""
if command -v sudo &> /dev/null; then
    SUDO_CMD="sudo"
fi

REAL_HOME=""
EXEC_USER_CMD=""
if [ -n "${SUDO_USER}" ]; then
  REAL_HOME=$(getent passwd "${SUDO_USER}" | cut -d: -f6)
  EXEC_USER_CMD="$SUDO_CMD -u ${SUDO_USER}"
else
  REAL_HOME="${HOME}"
fi

echo "Installing Oh My Zsh..."

if [ -d "${REAL_HOME}/.oh-my-zsh" ]; then
    echo "Oh My Zsh is already installed. Skipping installation."
else
    ${EXEC_USER_CMD} sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)" "" --unattended
fi

echo "Oh My Zsh installation script finished."