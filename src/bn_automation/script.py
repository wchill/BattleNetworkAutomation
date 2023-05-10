import collections
import time
from typing import Any, Callable, Optional, Tuple

from . import image_processing
from .controller import Button, Command, Controller, DPad

DEFAULT_HOLD_TIME = 80


class Script:
    def __init__(self, controller: Controller):
        self.controller = controller
        self.last_inputs = collections.deque(maxlen=20)

    def _send_cmd(self, command: Command):
        self.last_inputs.append(command)
        self.controller.send_cmd(command)

    def _press_dpad(self, dpad: DPad, hold_time: int, wait_time: int):
        if wait_time is None or wait_time < 0:
            wait_time = hold_time
        self._send_cmd(Command().dpad(dpad).hold(hold_time))
        self._send_cmd(Command().hold(wait_time))
        self.controller.p_wait((hold_time + wait_time) / 1000.0)

    def _press_button(self, button: Button, hold_time: int, wait_time: int):
        if wait_time is None or wait_time < 0:
            wait_time = hold_time
        self._send_cmd(Command().press(button).hold(hold_time))
        self._send_cmd(Command().hold(wait_time))
        self.controller.p_wait((hold_time + wait_time) / 1000.0)

    @staticmethod
    def repeat(func: Callable[..., Any], times: int, *args: Any, **kwargs: Any):
        for _ in range(times):
            func(*args, **kwargs)

    def up(self, hold_time: int = 200, wait_time: int = None):
        self._press_dpad(DPad.Up, hold_time, wait_time)

    def down(self, hold_time: int = DEFAULT_HOLD_TIME, wait_time: int = None):
        self._press_dpad(DPad.Down, hold_time, wait_time)

    def left(self, hold_time: int = DEFAULT_HOLD_TIME, wait_time: int = None):
        self._press_dpad(DPad.Left, hold_time, wait_time)

    def right(self, hold_time: int = DEFAULT_HOLD_TIME, wait_time: int = None):
        self._press_dpad(DPad.Right, hold_time, wait_time)

    def up_left(self, hold_time: int = DEFAULT_HOLD_TIME, wait_time: int = None):
        self._press_dpad(DPad.UpLeft, hold_time, wait_time)

    def up_right(self, hold_time: int = DEFAULT_HOLD_TIME, wait_time: int = None):
        self._press_dpad(DPad.UpRight, hold_time, wait_time)

    def down_left(self, hold_time: int = DEFAULT_HOLD_TIME, wait_time: int = None):
        self._press_dpad(DPad.DownLeft, hold_time, wait_time)

    def down_right(self, hold_time: int = DEFAULT_HOLD_TIME, wait_time: int = None):
        self._press_dpad(DPad.DownRight, hold_time, wait_time)

    def a(self, hold_time: int = DEFAULT_HOLD_TIME, wait_time: int = None):
        self._press_button(Button.A, hold_time, wait_time)

    def b(self, hold_time: int = DEFAULT_HOLD_TIME, wait_time: int = None):
        self._press_button(Button.B, hold_time, wait_time)

    def x(self, hold_time: int = DEFAULT_HOLD_TIME, wait_time: int = None):
        self._press_button(Button.X, hold_time, wait_time)

    def y(self, hold_time: int = DEFAULT_HOLD_TIME, wait_time: int = None):
        self._press_button(Button.Y, hold_time, wait_time)

    def l(self, hold_time: int = DEFAULT_HOLD_TIME, wait_time: int = None):
        self._press_button(Button.L, hold_time, wait_time)

    def r(self, hold_time: int = DEFAULT_HOLD_TIME, wait_time: int = None):
        self._press_button(Button.R, hold_time, wait_time)

    def zl(self, hold_time: int = DEFAULT_HOLD_TIME, wait_time: int = None):
        self._press_button(Button.ZL, hold_time, wait_time)

    def zr(self, hold_time: int = DEFAULT_HOLD_TIME, wait_time: int = None):
        self._press_button(Button.ZR, hold_time, wait_time)

    def plus(self, hold_time: int = DEFAULT_HOLD_TIME, wait_time: int = None):
        self._press_button(Button.Plus, hold_time, wait_time)

    def minus(self, hold_time: int = DEFAULT_HOLD_TIME, wait_time: int = None):
        self._press_button(Button.Minus, hold_time, wait_time)

    def l3(self, hold_time: int = DEFAULT_HOLD_TIME, wait_time: int = None):
        self._press_button(Button.L3, hold_time, wait_time)

    def r3(self, hold_time: int = DEFAULT_HOLD_TIME, wait_time: int = None):
        self._press_button(Button.R3, hold_time, wait_time)

    def home(self, hold_time: int = DEFAULT_HOLD_TIME, wait_time: int = None):
        self._press_button(Button.Home, hold_time, wait_time)

    def wait(self, wait_time: int = DEFAULT_HOLD_TIME):
        self.last_inputs.append(wait_time)
        self.controller.p_wait(wait_time / 1000.0)

    @staticmethod
    def wait_for_text(
        matcher: Callable[[str], bool],
        top_left: Tuple[int, int],
        size: Tuple[int, int],
        timeout: Optional[float],
        invert=True,
    ) -> bool:
        start_time = time.time()
        # last_ocr_text = None
        while timeout is None or start_time + timeout > time.time():
            ocr_text = image_processing.run_tesseract_line(image_processing.capture(), top_left, size, invert)
            # if last_ocr_text != ocr_text:
            #     last_ocr_text = ocr_text
            #     print("OCR text: " + last_ocr_text)
            if matcher(ocr_text):
                return True
            time.sleep(0.1)
        return False
