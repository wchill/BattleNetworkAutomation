#!/usr/bin/env bash
DIR="$( dirname -- "${BASH_SOURCE[0]}"; )";   # Get the directory name
DIR="$( realpath -e -- "$DIR"; )";    # Resolve its full path if need be
SRC_DIR="$( realpath -e -- "$DIR/../../.."; )"

appendfile() {
  line=$1
  f=$2
  echo "Adding '$line' to $f" && (grep -qxF "$line" $f || echo "$line" >> $f)
}

# TODO: create virtualenv and stuff
if [[ ! -d "$SRC_DIR/venv" ]] ; then
  echo "Creating python virtualenv"
  python3 -m pip install virtualenv
  python3 -m virtualenv "$SRC_DIR/venv"
  "$SRC_DIR/venv/bin/python" -m pip install -e "$SRC_DIR"
fi

echo "Writing udev rule for TC358743 HDMI module"
echo 'KERNEL=="video[0-9]*", SUBSYSTEM=="video4linux", KERNELS=="fe801000.csi|fe801000.csi1", ATTR{name}=="unicam-image", SYMLINK+="hdmi-capture", TAG+="systemd"' > /usr/lib/udev/rules.d/90-tc358743.rules

# Load the needed modules on boot
TEXT='dtoverlay=dwc2'
FILE='/boot/config.txt'
appendfile $TEXT $FILE

TEXT='dtoverlay=tc358743'
appendfile $TEXT $FILE

MODLOADFILE='/etc/modules-load.d/usbhid.conf'
echo "Writing modules-load.d conf to $MODLOADFILE"
cat << EOF | sudo tee $MODLOADFILE > /dev/null
dwc2
tc358743
libcomposite
v4l2loopback
xpad
EOF

MODFILE='/etc/modprobe.d/v4l2loopback.conf'
echo "Writing modprobe conf to $MODFILE"
cat << EOF | sudo tee $MODFILE > /dev/null
options v4l2loopback video_nr=100,101
options v4l2loopback card_label="Screen capture loopback"
EOF

# Create systemd service file
UNITFILE='/etc/systemd/system/tc358743.service'
echo "Writing tc358743 service file to $UNITFILE"
cat << EOF | sudo tee $UNITFILE > /dev/null
[Unit]
Description=EDID loader for TC358743
After=systemd-modules-load.service

[Service]
Type=oneshot
ExecStart=/usr/bin/env bash $DIR/init_tc358743.sh
ExecStop=/bin/true
RemainAfterExit=true

[Install]
WantedBy=multi-user.target
EOF

UNITFILE='/etc/systemd/system/v4l2loopback.service'
echo "Writing v4l2loopback service file to $UNITFILE"
cat << EOF | sudo tee $UNITFILE > /dev/null
[Unit]
Description=V4L2 loopback feeder
After=tc358743.service

[Service]
Type=simple
ExecStart=/usr/bin/ffmpeg -f video4linux2 -input_format bgr24 -video_size 1280x720 -vsync 2 -i /dev/hdmi-capture -codec copy -f v4l2 /dev/video100 -filter:v fps=30 -codec h264_v4l2m2m -f v4l2 -b:v 3M -fflags nobuffer /dev/video101
Restart=always

[Install]
WantedBy=multi-user.target
EOF

UNITFILE='/etc/systemd/system/v4l2rtspserver.service'
echo "Writing v4l2rtspserver service file to $UNITFILE"
cat << EOF | sudo tee $UNITFILE > /dev/null
[Unit]
Description=V4L2 RTSP server
After=v4l2loopback.service

[Service]
Type=simple
ExecStart=v4l2rtspserver -S1 -f -Q 3 /dev/video101
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

UNITFILE='/etc/systemd/system/usb-gadget.service'
STARTUP_CMD="$SRC_DIR/venv/bin/python -u $DIR/start_server.py > /dev/null"
echo "Writing usbgadget service file to $UNITFILE"
cat << EOF | sudo tee $UNITFILE > /dev/null
[Unit]
Description=USB gadget initialization
After=systemd-networkd-wait-online.service
Wants=systemd-networkd-wait-online.service
[Service]
Type=simple
ExecStart=$STARTUP_CMD
Restart=always
StandardOutput=journal+console
[Install]
WantedBy=sysinit.target
EOF

UNITFILE='/etc/systemd/system/discord-bot.service'
STARTUP_CMD="$SRC_DIR/venv/bin/python -u $SRC_DIR/discord_bot.py > /dev/null"
echo "Writing discord bot service file to $UNITFILE"
cat << EOF | sudo tee $UNITFILE > /dev/null
[Unit]
Description=Mr. Prog Discord bot
After=systemd-networkd-wait-online.service usb-gadget.service v4l2loopback.service
Wants=systemd-networkd-wait-online.service usb-gadget.service v4l2loopback.service
[Service]
Type=simple
ExecStart=$STARTUP_CMD
Restart=always
StandardOutput=journal+console
[Install]
WantedBy=sysinit.target
EOF
systemctl daemon-reload
systemctl enable usb-gadget
systemctl enable tc358743
systemctl enable v4l2loopback
systemctl enable v4l2rtspserver
systemctl enable discord-bot

echo "Setup done, you might need to reboot"
