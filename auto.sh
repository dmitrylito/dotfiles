#!/bin/bash
set -e

SUDO=""
BASEDIR=$(dirname "$0")
LOG_FILE=${BASEDIR}/logs/install.log

# Write function that prints a log (including time) to the console and to a file.
function log() {
  echo "$(date) - $1" | tee -a "${LOG_FILE}"
}

function create_folder() {
  if [[ ! -d "$1" ]]; then
    mkdir -p "$1"
    log "Folder $1 created."
  fi
}

# Check if a program exists, returning true if it does and false otherwise.
function program_exists() {
  command -v "$1" >/dev/null 2>&1
}

function help() {
  echo "Usage: ./install.sh [OPTIONS]"
  echo "Options:"
  echo "  -p, --package <package_name>  Install only the specified package."
  echo "  Example: ./install.sh -p nvim"
  echo "  Command above, -p, can be replaced by the env variable, DOTFILE_PACKAGES."
  echo "  Example: DOTFILE_PACKAGES=\"nvim stow\" ./install.sh"
  echo "  -d, --dotfiles                Install dotfiles."
  echo "  -h, --help                    Show this help message."
  exit 0
}

# Check if sudo exists:
if program_exists "sudo" >/dev/null 2>&1; then
  SUDO="sudo"
fi

# N num of arguments which contain the name of those packages that we want to install:
packages=()
prev_package=false
while [[ $# -gt 0 ]]; do
  key="$1"
  case $key in
  -p | --package)
    shift
    install_packages=true
    prev_package=true
    ;;
  -h | --help)
    prev_package=false
    shift
    help
    ;;
  -d | --dotfiles)
    prev_package=false
    install_dotfiles=true
    shift
    ;;
  *)
    if [[ $prev_package == true ]]; then
      packages+=("$1")
    else
      echo "Error: Invalid argument $1."
      exit 1
    fi
    shift
    ;;
  esac
done

# Check if the DOTFILE_PACKAGES env variable exists
if [[ -n "${DOTFILE_PACKAGES}" ]]; then
  # Split DOTFILE_PACKAGES into an array
  read -r -a packages <<<"${DOTFILE_PACKAGES}"
  install_packages=true
fi

# Install packages from ./packages/
if [[ -n "${install_packages}" ]]; then
  log "Installation of packages:"

  for file in "${BASEDIR}"/packages/*.sh; do
    filename=$(basename "$file")
    program="${filename%.*}"

    # Filter the programs that we want to install
    if [[ ${#packages[@]} -gt 0 ]]; then
      # Check if the program is in the packages list and continue if it is not there.
      if [[ ! " ${packages[*]} " =~ " ${program} " ]]; then
        log "Skipping $file. Not present in the arguments."
        continue
      fi
    else
      log "Install everything"
    fi

    if ! program_exists "${program}" >/dev/null 2>&1; then
      echo "Installing $file"
      ${SUDO} "$file" 2>&1
    else
      echo "Skipping installation: $file. Program already installed."
    fi | tee "${BASEDIR}/logs/${filename}.log"
  done

  log "Creation of config folder for current user:"
fi
# Resolve user/group/home robustly
USER_NAME="${USER:-$(id -un)}"
GROUP_NAME="${GROUP:-$(id -gn)}"
HOME_DIR="${HOME:-/home/${USER_NAME}}"

for folder in ".config" ".local" ".cache"; do
  folder_absolute="${HOME_DIR}/${folder}"

  create_folder "${folder_absolute}"

  # Only chown if user and group actually exist
  if getent passwd "${USER_NAME}" >/dev/null 2>&1 &&
    getent group "${GROUP_NAME}" >/dev/null 2>&1; then
    chown -R "${USER_NAME}:${GROUP_NAME}" "${folder_absolute}"
  else
    # Fall back to user-only, ignore errors
    chown -R "${USER_NAME}" "${folder_absolute}" 2>/dev/null || true
  fi
done

if [[ -n "${install_dotfiles}" ]]; then
  # Unlink all dotfiles
  stow --dir="$(pwd)"/dotfiles/ --target="$HOME" --verbose -D .
  # Link dotfiles again
  stow --dir="$(pwd)"/dotfiles/ --target="$HOME" --verbose .
fi
