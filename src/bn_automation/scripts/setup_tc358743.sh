#!/bin/bash

DIR="$( dirname -- "${BASH_SOURCE[0]}"; )";   # Get the directory name
DIR="$( realpath -e -- "$DIR"; )";    # Resolve its full path if need be

# Set EDID
v4l2-ctl --set-edid=file="$DIR/edid.txt"

# Set timings
v4l2-ctl --set-dv-bt-timings query
