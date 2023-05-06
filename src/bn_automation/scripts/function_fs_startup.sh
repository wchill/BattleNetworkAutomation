#!/bin/bash
# modprobe libcomposite
DIR="$( dirname -- "${BASH_SOURCE[0]}"; )";   # Get the directory name
DIR="$( realpath -e -- "$DIR"; )";    # Resolve its full path if need be
cd "$DIR/../" || exit

source venv/bin/activate
python scripts/function_fs_server.py
