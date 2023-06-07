import asyncio
import time
from typing import Any, Awaitable, Callable, Coroutine, Optional, Tuple

from ..controller import Button, Command, Controller, DPad
from . import image_processing
from .image_processing import Size, TopLeftCoords

# TODO: Evaluate whether we need 160 or can revert to 80
DEFAULT_HOLD_TIME = 160


Matcher = Callable[[str], bool]
MatchHandler = Callable[[], Coroutine[Any, Any, Tuple[int, Optional[str]]]]
MatchArgs = Tuple[Matcher, MatchHandler, TopLeftCoords, Size, bool]


class Script:
    def __init__(self, controller: Controller):
        self.controller = controller

    def _send_cmd(self, command: Command):
        self.controller.send_cmd(command)

    async def _press_dpad(self, dpad: DPad, hold_time: int, wait_time: int) -> None:
        if wait_time is None or wait_time < 0:
            wait_time = hold_time
        self._send_cmd(Command().dpad(dpad).hold(hold_time))
        self._send_cmd(Command().hold(wait_time))
        # self.controller.p_wait((hold_time + wait_time) / 1000.0)
        await self.controller.wait_for_inputs()

    async def _press_button(self, button: Button, hold_time: int, wait_time: int) -> None:
        if wait_time is None or wait_time < 0:
            wait_time = hold_time
        self._send_cmd(Command().press(button).hold(hold_time))
        self._send_cmd(Command().hold(wait_time))
        # self.controller.p_wait((hold_time + wait_time) / 1000.0)
        await self.controller.wait_for_inputs()

    @staticmethod
    async def repeat(func: Callable[..., Awaitable[Any]], times: int, *args: Any, **kwargs: Any) -> None:
        for _ in range(times):
            await func(*args, **kwargs)

    async def up(self, hold_time: int = DEFAULT_HOLD_TIME, wait_time: int = None) -> None:
        await self._press_dpad(DPad.Up, hold_time, wait_time)

    async def down(self, hold_time: int = DEFAULT_HOLD_TIME, wait_time: int = None) -> None:
        await self._press_dpad(DPad.Down, hold_time, wait_time)

    async def left(self, hold_time: int = DEFAULT_HOLD_TIME, wait_time: int = None) -> None:
        await self._press_dpad(DPad.Left, hold_time, wait_time)

    async def right(self, hold_time: int = DEFAULT_HOLD_TIME, wait_time: int = None) -> None:
        await self._press_dpad(DPad.Right, hold_time, wait_time)

    async def up_left(self, hold_time: int = DEFAULT_HOLD_TIME, wait_time: int = None) -> None:
        await self._press_dpad(DPad.UpLeft, hold_time, wait_time)

    async def up_right(self, hold_time: int = DEFAULT_HOLD_TIME, wait_time: int = None) -> None:
        await self._press_dpad(DPad.UpRight, hold_time, wait_time)

    async def down_left(self, hold_time: int = DEFAULT_HOLD_TIME, wait_time: int = None) -> None:
        await self._press_dpad(DPad.DownLeft, hold_time, wait_time)

    async def down_right(self, hold_time: int = DEFAULT_HOLD_TIME, wait_time: int = None) -> None:
        await self._press_dpad(DPad.DownRight, hold_time, wait_time)

    async def a(self, hold_time: int = DEFAULT_HOLD_TIME, wait_time: int = None) -> None:
        await self._press_button(Button.A, hold_time, wait_time)

    async def b(self, hold_time: int = DEFAULT_HOLD_TIME, wait_time: int = None) -> None:
        await self._press_button(Button.B, hold_time, wait_time)

    async def x(self, hold_time: int = DEFAULT_HOLD_TIME, wait_time: int = None) -> None:
        await self._press_button(Button.X, hold_time, wait_time)

    async def y(self, hold_time: int = DEFAULT_HOLD_TIME, wait_time: int = None) -> None:
        await self._press_button(Button.Y, hold_time, wait_time)

    async def l(self, hold_time: int = DEFAULT_HOLD_TIME, wait_time: int = None) -> None:
        await self._press_button(Button.L, hold_time, wait_time)

    async def r(self, hold_time: int = DEFAULT_HOLD_TIME, wait_time: int = None) -> None:
        await self._press_button(Button.R, hold_time, wait_time)

    async def zl(self, hold_time: int = DEFAULT_HOLD_TIME, wait_time: int = None) -> None:
        await self._press_button(Button.ZL, hold_time, wait_time)

    async def zr(self, hold_time: int = DEFAULT_HOLD_TIME, wait_time: int = None) -> None:
        await self._press_button(Button.ZR, hold_time, wait_time)

    async def plus(self, hold_time: int = DEFAULT_HOLD_TIME, wait_time: int = None) -> None:
        await self._press_button(Button.Plus, hold_time, wait_time)

    async def minus(self, hold_time: int = DEFAULT_HOLD_TIME, wait_time: int = None) -> None:
        await self._press_button(Button.Minus, hold_time, wait_time)

    async def l3(self, hold_time: int = DEFAULT_HOLD_TIME, wait_time: int = None) -> None:
        await self._press_button(Button.L3, hold_time, wait_time)

    async def r3(self, hold_time: int = DEFAULT_HOLD_TIME, wait_time: int = None) -> None:
        await self._press_button(Button.R3, hold_time, wait_time)

    async def home(self, hold_time: int = DEFAULT_HOLD_TIME, wait_time: int = None) -> None:
        await self._press_button(Button.Home, hold_time, wait_time)

    async def wait(self, wait_time: int = DEFAULT_HOLD_TIME) -> None:
        await asyncio.sleep(wait_time / 1000.0)

    @staticmethod
    async def wait_for_text(
        matcher: Callable[[str], bool],
        top_left: Tuple[int, int],
        size: Tuple[int, int],
        timeout: Optional[float],
        invert: bool = True,
    ) -> bool:
        start_time = time.time()
        while timeout is None or start_time + timeout > time.time():
            ocr_text = image_processing.run_tesseract_line(image_processing.capture(), top_left, size, invert)
            if matcher(ocr_text):
                return True
            await asyncio.sleep(0.1)
        return False

    @staticmethod
    async def match(*matchers: MatchArgs) -> Optional[Tuple[int, Optional[str]]]:
        frame = image_processing.capture()
        for matcher, run_func, top_left, size, invert in matchers:
            ocr_text = image_processing.run_tesseract_line(frame, top_left, size, invert)
            if matcher(ocr_text):
                return await run_func()

        return None

    @staticmethod
    async def wait_for_match(*matchers: MatchArgs, timeout: Optional[float]) -> Tuple[int, Optional[str]]:
        start_time = time.time()
        while timeout is None or start_time + timeout > time.time():
            frame = image_processing.capture()
            for matcher, run_func, top_left, size, invert in matchers:
                ocr_text = image_processing.run_tesseract_line(frame, top_left, size, invert)
                if matcher(ocr_text):
                    return await run_func()
            await asyncio.sleep(0.1)
        raise TimeoutError("Did not match within timeout")
