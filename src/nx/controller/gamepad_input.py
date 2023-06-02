import os
from typing import BinaryIO, Callable, Dict, Optional

import libevdev
from pyudev import Context, Monitor, MonitorObserver

available_gamepads: Dict[str, "Gamepad"] = {}
_observer: Optional[MonitorObserver] = None


def print_capabilities(device):
    v = device.driver_version
    print("Input driver version is {}.{}.{}".format(v >> 16, (v >> 8) & 0xFF, v & 0xFF))
    device.id
    print(
        "Input device ID: bus {:#x} vendor {:#x} product {:#x} version {:#x}".format(
            device.id["bustype"],
            device.id["vendor"],
            device.id["product"],
            device.id["version"],
        )
    )
    print("Input device name: {}".format(device.name))
    print("Supported events:")

    for t, cs in device.evbits.items():
        print("  Event type {} ({})".format(t.value, t.name))

        for c in cs:
            if t in [libevdev.EV_LED, libevdev.EV_SND, libevdev.EV_SW]:
                v = device.value[c]
                print("    Event code {} ({}) state {}".format(c.value, c.name, v))
            else:
                print("    Event code {} ({})".format(c.value, c.name))

            if t == libevdev.EV_ABS:
                a = device.absinfo[c]
                print("       {:10s} {:6d}".format("Value", a.value))
                print("       {:10s} {:6d}".format("Minimum", a.minimum))
                print("       {:10s} {:6d}".format("Maximum", a.maximum))
                print("       {:10s} {:6d}".format("Fuzz", a.fuzz))
                print("       {:10s} {:6d}".format("Flat", a.flat))
                print("       {:10s} {:6d}".format("Resolution", a.resolution))

    print("Properties:")
    for p in device.properties:
        print("  Property type {} ({})".format(p.value, p.name))


def print_event(e):
    print("Event: time {}.{:06d}, ".format(e.sec, e.usec), end="")
    if e.matches(libevdev.EV_SYN):
        if e.matches(libevdev.EV_SYN.SYN_MT_REPORT):
            print("++++++++++++++ {} ++++++++++++".format(e.code.name))
        elif e.matches(libevdev.EV_SYN.SYN_DROPPED):
            print(">>>>>>>>>>>>>> {} >>>>>>>>>>>>".format(e.code.name))
        else:
            print("-------------- {} ------------".format(e.code.name))
    else:
        print(
            "type {:02x} {} code {:03x} {:20s} value {:4d}".format(
                e.type.value, e.type.name, e.code.value, e.code.name, e.value
            )
        )


class Gamepad:
    def __init__(self, fd: BinaryIO, device: libevdev.Device):
        self.fd = fd
        self.device = device
        self.handle_button_changed_callback: Optional[Callable[[str, bool], None]] = None
        self.handle_axis_changed_callback: Optional[Callable[[str, float], None]] = None
        self.axis_info = {axis.name: device.absinfo[axis] for axis in self.device.evbits[libevdev.EV_ABS]}

    @property
    def button_name_map(self) -> Dict[str, str]:
        return {
            "BTN_SOUTH": "B",
            "BTN_NORTH": "Y",
            "BTN_EAST": "A",
            "BTN_WEST": "X",
            "BTN_TL": "L",
            "BTN_TR": "R",
            "BTN_MODE": "Home",
            "BTN_SELECT": "Minus",
            "BTN_START": "Plus",
            "BTN_THUMBL": "L3",
            "BTN_THUMBR": "R3",
        }

    @property
    def axis_name_map(self) -> Dict[str, str]:
        return {
            "ABS_Z": "ZL",
            "ABS_RZ": "ZR",
            "ABS_X": "LEFT_X",
            "ABS_Y": "LEFT_Y",
            "ABS_RX": "RIGHT_X",
            "ABS_RY": "RIGHT_Y",
            "ABS_HAT0X": "DPAD_X",
            "ABS_HAT0Y": "DPAD_Y",
        }

    def scale_axis(self, axis: str, value: int) -> float:
        axis_info = self.axis_info[axis]
        axis_range = axis_info.maximum - axis_info.minimum
        scaled_value = float(value - axis_info.minimum) / float(axis_range)
        return scaled_value * 2.0 - 1

    def process_updates(self):
        while True:
            try:
                for e in self.device.events():
                    if e.matches(libevdev.EV_KEY):
                        if self.handle_button_changed_callback is not None:
                            button_name = self.button_name_map.get(e.code.name, e.code.name)
                            self.handle_button_changed_callback(button_name, e.value == 1)
                    elif e.matches(libevdev.EV_ABS):
                        if self.handle_axis_changed_callback is not None:
                            axis_name = self.axis_name_map.get(e.code.name, e.code.name)
                            self.handle_axis_changed_callback(axis_name, self.scale_axis(e.code.name, e.value))
            except libevdev.EventsDroppedException:
                for e in self.device.sync():
                    print_event(e)
            except OSError:
                if not os.path.exists(self.fd.name):
                    self.fd.close()
                    break
            except ValueError:
                # Closed file
                break


class EightBitDoUltimateController(Gamepad):
    @Gamepad.button_name_map.getter
    def button_name_map(self) -> Dict[str, str]:
        return {
            "BTN_SOUTH": "B",
            "BTN_NORTH": "Y",
            "BTN_EAST": "A",
            "BTN_WEST": "X",
            "BTN_TL": "L",
            "BTN_TR": "R",
            "BTN_MODE": "Home",
            "BTN_SELECT": "Minus",
            "BTN_START": "Plus",
            "BTN_THUMBL": "L3",
            "BTN_THUMBR": "R3",
        }

    @Gamepad.axis_name_map.getter
    def axis_name_map(self) -> Dict[str, str]:
        return {
            "ABS_Z": "ZL",
            "ABS_RZ": "ZR",
            "ABS_X": "LEFT_X",
            "ABS_Y": "LEFT_Y",
            "ABS_RX": "RIGHT_X",
            "ABS_RY": "RIGHT_Y",
            "ABS_HAT0X": "DPAD_X",
            "ABS_HAT0Y": "DPAD_Y",
        }


gamepad_class_mapping = {"8BitDo Ultimate Wireless / Pro 2 Wired Controller": EightBitDoUltimateController}


def make_gamepad(device_path) -> Gamepad:
    fd = open("/dev/input/" + os.path.split(device_path)[-1], "rb")
    dev = libevdev.Device(fd)
    gamepad_class = gamepad_class_mapping.get(dev.name, Gamepad)
    return gamepad_class(fd, dev)


def monitor_gamepads(cv) -> None:
    global available_gamepads, _observer

    if _observer is None:

        def handle_device_event(event):
            try:
                if not os.path.split(event.device_path)[-1].startswith("event"):
                    return
                if event.action == "add":
                    with cv:
                        available_gamepads[event.device_path] = make_gamepad(event.device_path)
                        print(f"Added device {event.device_path}")
                        cv.notify_all()
                elif event.action == "remove" and event.device_path in available_gamepads:
                    with cv:
                        available_gamepads.pop(event.device_path)
                        print(f"Removed device {event.device_path}")
                else:
                    print(f"Unhandled action: {event.action} for {event}")
            except Exception:
                import traceback

                traceback.print_exc()

        context = Context()
        for device in context.list_devices(subsystem="input", ID_INPUT_JOYSTICK="1"):
            if os.path.split(device.device_path)[-1].startswith("event"):
                with cv:
                    available_gamepads[device.device_path] = make_gamepad(device.device_path)
                    cv.notify_all()

        monitor = Monitor.from_netlink(context)
        monitor.filter_by(subsystem="input")
        # noinspection PyTypeChecker
        _observer = MonitorObserver(monitor, callback=handle_device_event, name="monitor-observer")
        _observer.start()
