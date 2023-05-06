import time
from typing import Callable, Optional, Tuple

import cv2 as cv

from . import image_processing
from .controller import Button, Controller, DPad


class Script:
    def __init__(self, controller: Controller, capture: cv.VideoCapture):
        self.controller = controller
        self.capture = capture

    def _press_dpad(self, dpad: DPad, hold_time: float, wait_time: float):
        if wait_time is None or wait_time < 0:
            wait_time = hold_time
        self.controller.press_dpad(dpad, hold_time, wait_time)

    def _press_button(self, button: Button, hold_time: float, wait_time: float):
        if wait_time is None or wait_time < 0:
            wait_time = hold_time
        self.controller.press_button(button, hold_time, wait_time)

    def up(self, hold_time: float = 0.2, wait_time: float = None):
        self._press_dpad(DPad.Up, hold_time, wait_time)

    def down(self, hold_time: float = 0.2, wait_time: float = None):
        self._press_dpad(DPad.Down, hold_time, wait_time)

    def left(self, hold_time: float = 0.2, wait_time: float = None):
        self._press_dpad(DPad.Left, hold_time, wait_time)

    def right(self, hold_time: float = 0.2, wait_time: float = None):
        self._press_dpad(DPad.Right, hold_time, wait_time)

    def up_left(self, hold_time: float = 0.2, wait_time: float = None):
        self._press_dpad(DPad.UpLeft, hold_time, wait_time)

    def up_right(self, hold_time: float = 0.2, wait_time: float = None):
        self._press_dpad(DPad.UpRight, hold_time, wait_time)

    def down_left(self, hold_time: float = 0.2, wait_time: float = None):
        self._press_dpad(DPad.DownLeft, hold_time, wait_time)

    def down_right(self, hold_time: float = 0.2, wait_time: float = None):
        self._press_dpad(DPad.DownRight, hold_time, wait_time)

    def a(self, hold_time: float = 0.2, wait_time: float = None):
        self._press_button(Button.A, hold_time, wait_time)

    def b(self, hold_time: float = 0.2, wait_time: float = None):
        self._press_button(Button.B, hold_time, wait_time)

    def x(self, hold_time: float = 0.2, wait_time: float = None):
        self._press_button(Button.X, hold_time, wait_time)

    def y(self, hold_time: float = 0.2, wait_time: float = None):
        self._press_button(Button.Y, hold_time, wait_time)

    def l(self, hold_time: float = 0.2, wait_time: float = None):
        self._press_button(Button.L, hold_time, wait_time)

    def r(self, hold_time: float = 0.2, wait_time: float = None):
        self._press_button(Button.R, hold_time, wait_time)

    def zl(self, hold_time: float = 0.2, wait_time: float = None):
        self._press_button(Button.ZL, hold_time, wait_time)

    def zr(self, hold_time: float = 0.2, wait_time: float = None):
        self._press_button(Button.ZR, hold_time, wait_time)

    def plus(self, hold_time: float = 0.2, wait_time: float = None):
        self._press_button(Button.Plus, hold_time, wait_time)

    def minus(self, hold_time: float = 0.2, wait_time: float = None):
        self._press_button(Button.Minus, hold_time, wait_time)

    def l3(self, hold_time: float = 0.2, wait_time: float = None):
        self._press_button(Button.L3, hold_time, wait_time)

    def r3(self, hold_time: float = 0.2, wait_time: float = None):
        self._press_button(Button.R3, hold_time, wait_time)

    def wait(self, wait_time: float = 0.2):
        self.controller.p_wait(wait_time)

    def wait_for_text(
        self,
        matcher: Callable[[str], bool],
        top_left: Tuple[int, int],
        size: Tuple[int, int],
        timeout: Optional[float],
        invert=True,
    ) -> bool:
        start_time = time.time()
        while timeout is None or start_time + timeout > time.time():
            _, frame = self.capture.read()
            ocr_text = image_processing.run_tesseract_line(frame, top_left, size, invert)
            if matcher(ocr_text):
                return True
        return False

    def screen_capture(self, filename="frame.png"):
        _, frame = self.capture.read()
        cv.imwrite(filename, frame)
