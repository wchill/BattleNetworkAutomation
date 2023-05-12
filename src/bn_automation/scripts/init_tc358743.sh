#!/usr/bin/env bash
DIR="$( dirname -- "${BASH_SOURCE[0]}"; )";   # Get the directory name
DIR="$( realpath -e -- "$DIR"; )";    # Resolve its full path if need be
/usr/bin/v4l2-ctl --device=/dev/hdmi-capture --set-edid=file=$DIR/edid.txt --fix-edid-checksums --info-edid

while /usr/bin/v4l2-ctl --set-dv-bt-timings query 2>&1 | grep 'VIDIOC_S_DV_TIMINGS' &> /dev/null
do
  echo "Sleeping 3 seconds"
done
