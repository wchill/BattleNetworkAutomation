# https://github.com/Toufool/AutoSplit/blob/master/src/capture_method/WindowsGraphicsCaptureMethod.py
from __future__ import annotations

import asyncio
import platform
import sys
from ctypes import windll
from typing import cast

import cv2
import numpy as np
import win32gui
from winsdk.windows.ai.machinelearning import (
    LearningModelDevice,
    LearningModelDeviceKind,
)
from winsdk.windows.graphics import SizeInt32
from winsdk.windows.graphics.capture import (
    Direct3D11CaptureFramePool,
    GraphicsCaptureSession,
)
from winsdk.windows.graphics.capture.interop import create_for_window
from winsdk.windows.graphics.directx import DirectXPixelFormat
from winsdk.windows.graphics.imaging import BitmapBufferAccessMode, SoftwareBitmap
from winsdk.windows.media.capture import MediaCapture

RGBA_CHANNEL_COUNT = 4
WINDOWS_BUILD_NUMBER = int(platform.version().split(".")[-1]) if sys.platform == "win32" else -1
WGC_NO_BORDER_MIN_BUILD = 20348


def get_direct3d_device():
    # Note: Must create in the same thread (can't use a global) otherwise when ran from LiveSplit it will raise:
    # OSError: The application called an interface that was marshalled for a different thread
    media_capture = MediaCapture()

    async def init_mediacapture():
        await (media_capture.initialize_async() or asyncio.sleep(0))

    # TODO: This deadlocks or something but it doesn't work right now
    fut = asyncio.run_coroutine_threadsafe(init_mediacapture(), asyncio.get_running_loop())
    fut.result()

    direct_3d_device = media_capture.media_capture_settings and media_capture.media_capture_settings.direct3_d11_device
    if not direct_3d_device:
        try:
            # May be problematic? https://github.com/pywinrt/python-winsdk/issues/11#issuecomment-1315345318
            direct_3d_device = LearningModelDevice(LearningModelDeviceKind.DIRECT_X_HIGH_PERFORMANCE).direct3_d11_device
        # TODO: Unknown potential error, I don't have an older Win10 machine to test.
        except BaseException:  # noqa: S110,BLE001
            pass
    if not direct_3d_device:
        raise OSError("Unable to initialize a Direct3D Device.")
    return direct_3d_device


def is_valid_hwnd(hwnd: int):
    """Validate the hwnd points to a valid window and not the desktop or whatever window obtained with `""`."""
    if not hwnd:
        return False
    if sys.platform == "win32":
        # TODO: Fix stubs, IsWindow should return a boolean
        return bool(win32gui.IsWindow(hwnd) and win32gui.GetWindowText(hwnd))
    return True


class WindowsGraphicsCaptureMethod:
    size: SizeInt32
    frame_pool: Direct3D11CaptureFramePool | None = None
    session: GraphicsCaptureSession | None = None
    """This is stored to prevent session from being garbage collected"""
    last_captured_frame: cv2.Mat | None = None

    def __init__(self, captured_window_name: str):
        windll.user32.SetProcessDPIAware()
        hwnd = win32gui.FindWindow(None, captured_window_name)

        if not is_valid_hwnd(hwnd):
            raise RuntimeError("Invalid handle")

        win32gui.ShowWindow(hwnd, 9)
        item = create_for_window(hwnd)
        frame_pool = Direct3D11CaptureFramePool.create_free_threaded(
            get_direct3d_device(),
            DirectXPixelFormat.B8_G8_R8_A8_UINT_NORMALIZED,
            1,
            item.size,
        )
        if not frame_pool:
            raise OSError("Unable to create a frame pool for a capture session.")
        session = frame_pool.create_capture_session(item)
        if not session:
            raise OSError("Unable to create a capture session.")
        session.is_cursor_capture_enabled = False
        if WINDOWS_BUILD_NUMBER >= WGC_NO_BORDER_MIN_BUILD:
            session.is_border_required = False
        session.start_capture()

        self.session = session
        self.size = item.size

        self.frame_pool = frame_pool
        self.hwnd = hwnd

    def close(self):
        if self.frame_pool:
            self.frame_pool.close()
            self.frame_pool = None
        if self.session:
            try:
                self.session.close()
            except OSError:
                # OSError: The application called an interface that was marshalled for a different thread
                # This still seems to close the session and prevent the following hard crash in LiveSplit
                # "AutoSplit.exe	<process started at 00:05:37.020 has terminated with 0xc0000409 (EXCEPTION_STACK_BUFFER_OVERRUN)>" # noqa: E501
                pass
            self.session = None

    def get_frame(self) -> tuple[cv2.Mat | None, bool]:
        x1, y1, x2, y2 = win32gui.GetClientRect(self.hwnd)
        client_width, client_height = x2 - x1, y2 - y1
        top_left = self.size.width - client_width - 1, self.size.height - client_height - 1
        client_size = client_width, client_height

        # Animating
        if client_size[0] <= 0 or client_size[1] <= 0:
            return None, False

        # win32gui.ShowWindow()
        # We still need to check the hwnd because WGC will return a blank black image
        if not (
            self.check_selected_region_exists(self.hwnd)
            # Only needed for the type-checker
            and self.frame_pool
        ):
            return None, False

        try:
            frame = self.frame_pool.try_get_next_frame()
        # Frame pool is closed
        except OSError:
            return None, False

        async def coroutine():
            # We were too fast and the next frame wasn't ready yet
            if not frame:
                return None
            return await (SoftwareBitmap.create_copy_from_surface_async(frame.surface) or asyncio.sleep(0, None))

        try:
            software_bitmap = asyncio.run(coroutine())
        except SystemError as exception:
            # HACK: can happen when closing the GraphicsCapturePicker
            if str(exception).endswith("returned a result with an error set"):
                return self.last_captured_frame, True
            raise

        if not software_bitmap:
            # HACK: Can happen when starting the region selector
            return self.last_captured_frame, True
            # raise ValueError("Unable to convert Direct3D11CaptureFrame to SoftwareBitmap.")
        bitmap_buffer = software_bitmap.lock_buffer(BitmapBufferAccessMode.READ_WRITE)
        if not bitmap_buffer:
            raise ValueError("Unable to obtain the BitmapBuffer from SoftwareBitmap.")
        reference = bitmap_buffer.create_reference()
        image = np.frombuffer(cast(bytes, reference), dtype=np.uint8)
        image.shape = (self.size.height, self.size.width, RGBA_CHANNEL_COUNT)
        image = image[top_left[1] : top_left[1] + client_size[1], top_left[0] : top_left[0] + client_size[0]]

        if image.shape[0] < client_height or image.shape[1] < client_width:
            print(image.shape)
            return None, False

        self.last_captured_frame = image
        return image, False

    def check_selected_region_exists(self, hwnd: int) -> bool:
        return bool(
            is_valid_hwnd(hwnd) and self.frame_pool and self.session,
        )
