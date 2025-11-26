#!/bin/bash
set -e

USER=$(ls /home/ | head -n1) # This can be problematic in case there are more than one users available.
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

# Check if a program exists, returing true if it does and false otherwise.
function program_exists() {
	command -v "$1" >/dev/null 2>&1
}

function help() {
	echo "Usage: ./install.sh [OPTIONS]"
	echo "Options:"
	echo "  -p, --package <package_name>  Install only the specified package."
	echo "  Example: ./install.sh -p nvim"
	echo "  Command above, -p, can be replaced by the env varialbe, DOTFILE_PACKAGES."
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
		# packages+=("$2")
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
		# unknown option
		shift # past argument
		;; 
	esac
done

# Check if the DOTFILE_PACKAGES env variable exists
if [[ -n "${DOTFILE_PACKAGES}" ]]; then
	packages=("${DOTFILE_PACKAGES:-}")
	install_packages=true
fi

# Bash fucntions that iterates through all the scriptsm from ./packages/
# and executes them one by one. The logs are saved in the current directory ./logs/
if [[ -n "${install_packages}" ]]; then
	log "Installation of pacackes: "
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

	log "Creation of config folders:"
	# Create config dotfiles ~/.config ~/.local/ ~/.cache/

	for folder in ".config" ".local" ".cache"; do
		folder_absolute="/home/${USER}/${folder}"
		create_folder "${folder_absolute}"
		chown -R "${USER}:${USER}" "${folder_absolute}"
	done
fi

if [ -n "${install_dotfiles}" ]; then
	# Unlink all dotfiles
	stow --dir="$(pwd)"/dotfiles/ --target="$HOME" --verbose -D .
	# Link dotfiles again
	stow --dir="$(pwd)"/dotfiles/ --target="$HOME" --verbose .
fi