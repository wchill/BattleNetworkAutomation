#!/usr/bin/env python3
import io
from typing import Optional, List
from utils.raw_inputs import RawDPad, _RawDPad, RawButton, ExtendedIntFlagEnum

import time
import math


Button = RawButton


class DPad(ExtendedIntFlagEnum):
    Center    = 0x00
    Up        = 0x01
    Right     = 0x02
    Down      = 0x04
    Left      = 0x08
    UpRight   = Up + Right
    DownRight = Down + Right
    UpLeft    = Up + Left
    DownLeft  = Down + Left


class _AnalogStick:
    SHIFT_BITS = 0

    @classmethod
    def angle(cls, value):
        return value << cls.SHIFT_BITS

    @classmethod
    def intensity(cls, value):
        return value << cls.SHIFT_BITS

    Right     = 0x000
    UpRight   = 0x02D
    Up        = 0x05A
    UpLeft    = 0x087
    Left      = 0x0B4
    DownLeft  = 0x0E1
    Down      = 0x10E
    DownRight = 0x13B

    # Intensity values
    Max  = 0xFF
    Min  = 0x00
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
        self.wait_time = 0

    def press(self, button):
        self._buttons |= button
        return self

    def release(self, button):
        self._buttons &= ~(1 << button)
        return self

    def dpad(self, dpad):
        self._dpad = dpad
        return self

    def stick_angle(self, angle):
        self._stick_angle = angle
        return self

    def stick_value(self, value):
        self._stick_intensity = value
        return self

    def left_angle(self, angle):
        return self.stick_angle(angle << LeftStick.SHIFT_BITS)

    def right_angle(self, angle):
        return self.stick_angle(angle << RightStick.SHIFT_BITS)

    def left_value(self, value):
        return self.stick_value(value << LeftStick.SHIFT_BITS)

    def right_value(self, value):
        return self.stick_value(value << RightStick.SHIFT_BITS)

    def sec(self, value):
        self.time = value
        return self

    def wait(self, value):
        self.wait_time = value
        return self

    def _translate_dpad(self):
        # ew
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

        left_angle = self._stick_angle & 0xFFFF
        right_angle = (self._stick_angle >> 16) & 0xFFFF
        left_intensity = self._stick_intensity & 0xFFFF
        right_intensity = (self._stick_intensity >> 16) & 0xFFFF

        left_x, left_y = self._translate_angle(left_angle, left_intensity)
        right_x, right_y = self._translate_angle(right_angle, right_intensity)

        packet = [button_low, button_high, dpad, left_x, left_y, right_x, right_y, 0x00]
        return packet

    def copy(self):
        c = Command()
        c.__dict__ = self.__dict__.copy()
        return c


class Controller:
    def __init__(self, output: io.IOBase):
        self.output = output
        self.last_command = Command()

    @staticmethod
    # Precision wait
    def p_wait(wait_time):
        t0 = time.perf_counter()
        t1 = t0
        while t1 - t0 < wait_time:
            t1 = time.perf_counter()

    def pprint_packet(self, bytestring):
        button = repr(RawButton.from_bytes(bytestring[:2], byteorder='little'))
        dpad = repr(RawDPad.from_bytes(b'\x00\x00' + bytestring[2:3], byteorder='little'))
        lx = int.from_bytes(bytestring[3:4], byteorder='little')
        ly = int.from_bytes(bytestring[4:5], byteorder='little')
        rx = int.from_bytes(bytestring[5:6], byteorder='little')
        ry = int.from_bytes(bytestring[6:7], byteorder='little')
        print(f'Buttons: {button}, DPad: {dpad}, LX: {lx}, LY: {ly}, RX: {rx}, RY: {ry}')

    def write_bytes(self, bytes_out: List[int]) -> int:
        bytestring = bytearray(bytes_out)
        # self.pprint_packet(bytestring)
        num_bytes = self.output.write(bytestring)
        self.output.flush()
        return num_bytes

    # Write byte to the serial port
    def write_byte(self, byte_out: int) -> int:
        return self.write_bytes([byte_out])

    # Send a raw packet and wait for a response
    def send_packet(self, packet: List[int], debug=False) -> bool:
        if not debug:
            self.write_bytes(packet)
        return True

    # Send a formatted controller command to the MCU
    def send_cmd(self, command: Optional[Command] = None) -> bool:
        if command is None:
            command = Command()

        bytes_written = 0

        # If time duration is specified, send command and then wait. Function will send previous command before return
        if command.time > 0:
            bytes_written = self.send_packet(command.to_packet())
            self.p_wait(command.time)
        else:
            # Update the last command sent
            self.last_command = command

        bytes_written += self.send_packet(self.last_command.to_packet())
        if command.wait_time > 0:
            self.p_wait(command.wait_time)
        return bytes_written

    def press_button(self, button: Button, hold_time: float = 0.2) -> "Controller":
        self.send_cmd(Command().press(button).sec(hold_time).wait(hold_time))
        return self

    def press_dpad(self, dpad: DPad, hold_time: float = 0.2) -> "Controller":
        self.send_cmd(Command().dpad(dpad).sec(hold_time).wait(hold_time))
        return self
