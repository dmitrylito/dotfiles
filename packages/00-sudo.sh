#!/bin/bash

# Sudo
if ! command -v sudo &> /dev/null
then
    echo "sudo could not be found, installing..."
    # This assumes the script is run as root if sudo is not available
    apt-get update && apt-get install -y sudo
else
    echo "sudo is already installed."
fi
