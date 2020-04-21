#!/bin/bash
modprobe libcomposite
cd /sys/kernel/config/usb_gadget/
mkdir -p pi4
cd pi4
echo 0x1d6b > idVendor # Linux Foundation
echo 0x0104 > idProduct # Multifunction Composite Gadget
echo 0x0100 > bcdDevice # v1.0.0
echo 0x0110 > bcdUSB # USB1.1 (full speed)

# Defined by interface descriptors
echo 0x00 > bDeviceClass
echo 0x00 > bDeviceSubClass
echo 0x00 > bDeviceProtocol

mkdir -p strings/0x409
echo "1337" > strings/0x409/serialnumber
echo "wchill" > strings/0x409/manufacturer
echo "BN6 Auto Battler" > strings/0x409/product

mkdir -p configs/c.1/strings/0x409
echo "USB game controller" > configs/c.1/strings/0x409/configuration
echo 500 > configs/c.1/MaxPower

# Add functions here
mkdir -p functions/hid.usb0
echo 3 > functions/hid.usb0/protocol
echo 0 > functions/hid.usb0/subclass
echo 8 > functions/hid.usb0/report_length
# TODO: we should add something here to dynamically generate the string.
echo -ne \\x05\\x01\\x09\\x05\\xa1\\x01\\x15\\x00\\x25\\x01\\x35\\x00\\x45\\x01\\x75\\x01\\x95\\x0e\\x05\\x09\\x19\\x01\\x29\\x0e\\x81\\x02\\x95\\x02\\x81\\x01\\x05\\x01\\x25\\x07\\x46\\x3b\\x01\\x75\\x04\\x95\\x01\\x65\\x14\\x09\\x39\\x81\\x42\\x65\\x00\\x95\\x01\\x81\\x01\\x26\\xff\\x00\\x46\\xff\\x00\\x09\\x30\\x09\\x31\\x09\\x32\\x09\\x35\\x75\\x08\\x95\\x04\\x81\\x02\\x75\\x08\\x95\\x01\\x81\\x01\\xc0 > functions/hid.usb0/report_desc
ln -s functions/hid.usb0 configs/c.1/

mkdir -p functions/acm.usb0
ln -s functions/acm.usb0 configs/c.1/
# End functions

ls /sys/class/udc > UDC
chmod 666 /dev/hidg0