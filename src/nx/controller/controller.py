import asyncio
import math
import time
from typing import List, Optional, Tuple

from .commands import ControllerRequest
from .raw_inputs import ExtendedIntFlagEnum, RawButton, RawDPad, _RawDPad

Button = RawButton


class DPad(ExtendedIntFlagEnum):
    Center = 0x00
    Up = 0x01
    Right = 0x02
    Down = 0x04
    Left = 0x08
    UpRight = Up + Right
    DownRight = Down + Right
    UpLeft = Up + Left
    DownLeft = Down + Left


class _AnalogStick:
    SHIFT_BITS = 0

    @classmethod
    def angle(cls, value):
        return value << cls.SHIFT_BITS

    @classmethod
    def intensity(cls, value):
        return value << cls.SHIFT_BITS

    Right = 0x000
    UpRight = 0x02D
    Up = 0x05A
    UpLeft = 0x087
    Left = 0x0B4
    DownLeft = 0x0E1
    Down = 0x10E
    DownRight = 0x13B

    # Intensity values
    Max = 0xFF
    Min = 0x00
    Half = 0x7F

    Intensity = [Min, Half, Max]
    Directions = [Right, UpRight, Up, UpLeft, Left, DownLeft, Down, DownRight]


class LeftStick(_AnalogStick):
    SHIFT_BITS = 0


class RightStick(_AnalogStick):
    SHIFT_BITS = 16


class Command:
    def __init__(self):
        self._buttons = 0
        self._dpad = DPad.Center
        self._stick_angle = 0
        self._stick_intensity = 0
        self.time = 0

    def press(self, button: Button) -> "Command":
        self._buttons |= button
        return self

    def release(self, button: Button) -> "Command":
        self._buttons &= ~(1 << button)
        return self

    def dpad(self, dpad: DPad) -> "Command":
        self._dpad = dpad
        return self

    def stick_angle(self, angle) -> "Command":
        self._stick_angle = angle
        return self

    def stick_value(self, value) -> "Command":
        self._stick_intensity = value
        return self

    def left_angle(self, angle) -> "Command":
        return self.stick_angle(angle << LeftStick.SHIFT_BITS)

    def right_angle(self, angle) -> "Command":
        return self.stick_angle(angle << RightStick.SHIFT_BITS)

    def left_value(self, value) -> "Command":
        return self.stick_value(value << LeftStick.SHIFT_BITS)

    def right_value(self, value) -> "Command":
        return self.stick_value(value << RightStick.SHIFT_BITS)

    def hold(self, value: int) -> "Command":
        self.time = value
        return self

    # noinspection PyTypeChecker
    @property
    def current_buttons(self) -> List[Button]:
        retval = []
        for button in Button:
            if self._buttons & button.value:
                retval.append(button)
        return retval

    @property
    def current_dpad(self) -> DPad:
        return self._dpad

    @property
    def current_left_stick(self) -> Tuple[int, int]:
        return self._stick_angle & 0xFFFF, self._stick_intensity & 0xFFFF

    @property
    def current_right_stick(self) -> Tuple[int, int]:
        return (self._stick_angle >> 16) & 0xFFFF, (self._stick_intensity >> 16) & 0xFFFF

    def _translate_dpad(self):
        # ew
        # noinspection PyTypeChecker
        return getattr(RawDPad, DPad(self._dpad).name) >> _RawDPad.SHIFT_BITS

    @staticmethod
    # Compute x and y based on angle and intensity
    def _translate_angle(angle, intensity):
        # y is negative because on the Y input, UP = 0 and DOWN = 255
        x = int((math.cos(math.radians(angle)) * 0x7F) * intensity / 0xFF) + 0x80
        y = -int((math.sin(math.radians(angle)) * 0x7F) * intensity / 0xFF) + 0x80
        return x, y

    def to_packet(self):
        button_low = self._buttons & 0xFF
        button_high = (self._buttons >> 8) & 0xFF
        dpad = self._translate_dpad()

        left_angle, left_intensity = self.current_left_stick
        right_angle, right_intensity = self.current_right_stick

        left_x, left_y = self._translate_angle(left_angle, left_intensity)
        right_x, right_y = self._translate_angle(right_angle, right_intensity)

        packet = [button_low, button_high, dpad, left_x, left_y, right_x, right_y, 0x00]
        return packet

    def copy(self):
        c = Command()
        c.__dict__ = self.__dict__.copy()
        return c


class Controller:
    def __init__(self, output):
        self.output = output
        self.last_input_finish_time = 0

    @staticmethod
    # Precision wait
    def p_wait(wait_time):
        t0 = time.perf_counter()
        t1 = t0
        while t1 - t0 < wait_time:
            t1 = time.perf_counter()

    async def wait_for_inputs(self):
        await asyncio.sleep(self.last_input_finish_time - time.time())

    @staticmethod
    def pprint_packet(bytestring):
        button = repr(RawButton.from_bytes(bytestring[:2], byteorder="little"))
        dpad = repr(RawDPad.from_bytes(b"\x00\x00" + bytestring[2:3], byteorder="little"))
        lx = int.from_bytes(bytestring[3:4], byteorder="little")
        ly = int.from_bytes(bytestring[4:5], byteorder="little")
        rx = int.from_bytes(bytestring[5:6], byteorder="little")
        ry = int.from_bytes(bytestring[6:7], byteorder="little")
        print(f"Buttons: {button}, DPad: {dpad}, LX: {lx}, LY: {ly}, RX: {rx}, RY: {ry}")

    # Send a formatted controller command to the MCU
    def send_cmd(self, command: Optional[Command] = None):
        if command is None:
            command = Command()

        if command.time is not None and command.time > 0:
            self.output.write(
                ControllerRequest.UPDATE_REPORT_FOR_MSEC,
                bytes(command.to_packet()) + command.time.to_bytes(length=4, byteorder="little"),
            )
            if self.last_input_finish_time is None:
                self.last_input_finish_time = time.time()
            self.last_input_finish_time += command.time / 1000
        else:
            self.output.write(ControllerRequest.UPDATE_REPORT, bytes(command.to_packet()))
            self.last_input_finish_time = time.time()

    def press_button(self, button: Button, hold_ms: int = 80, wait_ms: int = None) -> "Controller":
        if wait_ms is None:
            wait_ms = hold_ms
        self.send_cmd(Command().press(button).hold(hold_ms))
        self.send_cmd(Command().hold(wait_ms))
        return self

    def press_dpad(self, dpad: DPad, hold_ms: int = 80, wait_ms: int = None) -> "Controller":
        if wait_ms is None:
            wait_ms = hold_ms
        self.send_cmd(Command().dpad(dpad).hold(hold_ms))
        self.send_cmd(Command().hold(wait_ms))
        return self
