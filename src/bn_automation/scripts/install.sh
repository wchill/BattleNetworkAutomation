#!/bin/bash
DIR="$( dirname -- "${BASH_SOURCE[0]}"; )";   # Get the directory name
DIR="$( realpath -e -- "$DIR"; )";    # Resolve its full path if need be

appendfile() {
  line=$1
  f=$2
  echo "Adding '$line' to $f" && (grep -qxF "$line" $f || echo "$line" >> $f)
}

echo "Writing udev rule for TC358743 HDMI module"
echo ACTION=="add", SUBSYSTEM=="video4linux", ATTR\{name\}=="unicam-image", RUN+="$DIR/setup_tc358743.sh" > /usr/lib/udev/rules.d/90-tc358743.rules

# Load the needed modules on boot
TEXT='dtoverlay=dwc2'
FILE='/boot/config.txt'
appendfile $TEXT $FILE

TEXT='dtoverlay=tc358743'
appendfile $TEXT $FILE

TEXT='libcomposite'
FILE='/etc/modules'
appendfile $TEXT $FILE

# Create systemd service file
UNITFILE='/etc/systemd/system/usb-gadget.service'
STARTUP_SCRIPT="$DIR/function_fs_startup.sh"

echo "Writing systemd service file to $UNITFILE"

cat << EOF | sudo tee $UNITFILE > /dev/null
[Unit]
Description=USB gadget initialization
After=network-online.target
Wants=network-online.target
#After=systemd-modules-load.service
[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=$STARTUP_SCRIPT
[Install]
WantedBy=sysinit.target
EOF
systemctl daemon-reload

echo "Rebooting!"
reboot
