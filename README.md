# Automated BugFrag grinding for Battle Network Legacy Collection (Battle Network 6)

## Requirements
* Raspberry Pi Zero 2 W, 4 Model B, 400, or any other Pi that supports USB gadget mode.
  * For the 4 Model B and 400, you will either need to inject additional 5V power via the GPIO pins or use something
    like https://www.pishop.us/product/usb-c-pwr-splitter/ because the Switch dock cannot supply enough power to run
    the Pi without stability issues.
  * For Model A/A+ Pis, you need a USB A-A cable and need to modify `/boot/config.txt` to force the port into device
    mode. See https://raspberrypi.stackexchange.com/a/119077
  * I wouldn't recommend running this on a Zero, Zero W, or 1 Model A since they have only a single core.
* Elgato HD60 S+ / Cam Link / Cam Link 4k / some other capture card supported by OpenCV
  * Some capture cards might not work out of the box, so you may have to use screen capture.
  * Some capture cards might only allow exclusive access, so running this script will prevent OBS or other software from
    displaying video. You can use an HDMI splitter for this.
  * If using a USB capture card, you can connect it directly to the Raspberry Pi. However, be wary of power usage.

## Usage
1. Set up your Pi and enable networking, either Ethernet or Wi-Fi. Ethernet is preferable but either is fine.
2. Install `git`, `libaio1`, and `python3-pip`
    * `sudo apt update && sudo apt install -y git libaio1 python3-pip`
3. As root, edit `/boot/config.txt` to add the line `dtoverlay=dwc2` to the bottom
    * `sudo bash -c "echo "dtoverlay=dwc2" >> /boot/overlay.txt`
4. As root, edit `/etc/rc.local` to add the line `python $PROJECT_ROOT/function_fs_startup.sh` to the bottom _before_
   the line `exit 0`
    * Replace `$PROJECT_ROOT` with the correct folder path
5. As root, install python dependencies
    * `sudo -i`
    * `cd $PROJECT_ROOT`
    * `pip install -r requirements.txt`
6. Connect your Switch to your capture card
7. Go to Graveyard1 and set up your NCP/patch cards/folder according to this guide:
   https://www.reddit.com/r/BattleNetwork/comments/12tt38l/psa_the_fastest_bugfrag_farming_method_in_battle/
8. Press Home on your real controller, then navigate to Controllers > Change Grip/Order
    * It is very important that you do this, otherwise the game will not recognize accept input from the fake
    controller and the script will not work. In addition, the script assumes you are on this screen.
9. On whichever device the capture card is connected to, run the driver script: `python main.py`
    * If running on a different device, make sure to set up dependencies as before (step 3).
    * Running the Python driver script should work on any OS.

## How does it work?
The Raspberry Pi emulates a USB controller using USB gadget mode and Linux's functionfs driver that the bugfrag farmer
can control via a network socket. Using this, it's trivial to send inputs to the Switch. (Other implementations also
exist, such as controlling an emulated controller via serial port or using configfs to configure USB gadget mode)

The capture card lets us use OpenCV in order to capture image data from the Switch. Then, we perform some fuzzy image
matching to determine what state the game is in and use that knowledge to drive the state machine.

## Notes
* Connecting an 8BitDo controller in XInput mode will allow you to directly control the Switch. Press HOME to
  enable/disable this functionality. The script will automatically pause while you have direct control.
