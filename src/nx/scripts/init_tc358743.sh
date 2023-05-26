#!/usr/bin/env bash
DIR="$( dirname -- "${BASH_SOURCE[0]}"; )";   # Get the directory name
DIR="$( realpath -e -- "$DIR"; )";    # Resolve its full path if need be
/usr/bin/v4l2-ctl --device=/dev/hdmi-capture --set-edid=file="$DIR"/edid.txt --fix-edid-checksums --info-edid > /dev/null

echo "Set EDID, waiting for timings to be set"
while /usr/bin/v4l2-ctl --set-dv-bt-timings query 2>&1 | grep 'VIDIOC_S_DV_TIMINGS\|VIDIOC_QUERY_DV_TIMINGS' &> /dev/null
do
  /usr/bin/v4l2-ctl --device=/dev/hdmi-capture --set-edid=file="$DIR"/edid.txt --fix-edid-checksums --info-edid > /dev/null
  echo "Link severed, sleeping 3 seconds"
  sleep 3
done

systemd-notify READY=1

echo "Monitoring for HDMI disconnect"
while ! /usr/bin/v4l2-ctl --query-dv-timings 2>&1 | grep "Active width: 0" &> /dev/null
do
  sleep 10
done

echo "HDMI disconnected, exiting"
exit 1
