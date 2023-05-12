#!/usr/bin/env bash
DIR="$( dirname -- "${BASH_SOURCE[0]}"; )";   # Get the directory name
DIR="$( realpath -e -- "$DIR"; )";    # Resolve its full path if need be

sudo apt update
sudo apt install -y raspberrypi-bootloader raspberrypi-kernel raspberrypi-kernel-headers git build-essential vim python3-pip tesseract-ocr ffmpeg cmake

v4l2version=0.12.7
xpadversion=0.4
rm -rf /usr/src/v4l2loopback-${v4l2version}
git clone https://github.com/umlaeute/v4l2loopback.git /usr/src/v4l2loopback-${xpadversion}
dkms remove -m v4l2loopback -v ${v4l2version} --all
dkms add -m v4l2loopback -v ${v4l2version}
dkms build -m v4l2loopback -v ${v4l2version}
dkms install -m v4l2loopback -v ${v4l2version}
rm -rf /usr/src/xpad-${xpadversion}
git clone https://github.com/paroj/xpad.git /usr/src/xpad-${xpadversion}
dkms remove -m xpad -v 0.4 --all
dkms install -m xpad -v ${xpadversion}

git clone https://github.com/mpromonet/v4l2rtspserver.git /usr/src/v4l2rtspserver
cd /usr/src/v4l2rtspserver
cmake . && make -j 4 && make install

/usr/bin/env bash "$DIR/install.sh"
