import platform
import subprocess
import sys
from typing import Any, Optional, Tuple

import cv2 as cv
import numpy as np
import pytesseract
from PIL import Image

from nx.automation.WindowsGraphicsCaptureMethod import WindowsGraphicsCaptureMethod

LINUX_CAPTURE = None
LINUX_CAPTURE_DEVICES = [
    ("/dev/video100", lambda: None, False),
    ("/dev/hdmi-capture", lambda: subprocess.run(["/usr/bin/v4l2-ctl", "--set-dv-bt-timings", "query"]), True),
    (0, lambda: None, False),
]
LINUX_CAPTURE_BGR2RGB = False


def capture_linux(convert: bool = False, window_name: Optional[str] = None):
    global LINUX_CAPTURE, LINUX_CAPTURE_BGR2RGB
    if LINUX_CAPTURE is None:
        device = None
        for device, init_func, should_convert in LINUX_CAPTURE_DEVICES:
            print(f"Trying to open {device}")
            try:
                init_func()
                LINUX_CAPTURE = cv.VideoCapture(device)
                if not LINUX_CAPTURE.isOpened():
                    LINUX_CAPTURE = None
                    continue
                LINUX_CAPTURE_BGR2RGB = should_convert
                break
            except FileNotFoundError:
                continue
        if LINUX_CAPTURE is None:
            raise RuntimeError("Unable to open video capture device")
        else:
            print(f"Using {device}")
    try:
        frame = LINUX_CAPTURE.read()[1]
        if convert and LINUX_CAPTURE_BGR2RGB:
            frame = cv.cvtColor(frame, cv.COLOR_BGR2RGB)
        return frame
    except Exception:
        LINUX_CAPTURE = None
        # Try one time to reopen the capture device
        return capture_linux(convert)


WIN_HANDLES = None
WIN_CAPTURE = None


def capture_win(convert: bool = False, window_name: Optional[str] = None):
    import win32gui

    global WIN_CAPTURE
    if WIN_CAPTURE is None:
        assert window_name is not None
        WIN_CAPTURE = WindowsGraphicsCaptureMethod(window_name)

    img = None
    while img is None or img.shape[0] == 0 or img.shape[1] == 0:
        img, _ = WIN_CAPTURE.get_frame()
        if img is None:
            win32gui.ShowWindow(WIN_CAPTURE.hwnd, 9)

    return img


def capture_win_alt(convert: bool = False, window_name: Optional[str] = None):
    # Adapted from https://stackoverflow.com/questions/19695214/screenshot-of-inactive-window-printwindow-win32gui
    global WIN_HANDLES

    from ctypes import windll

    import win32gui
    import win32ui

    if WIN_HANDLES is None:
        assert window_name is not None
        print("Acquiring window handle")
        windll.user32.SetProcessDPIAware()
        hwnd = win32gui.FindWindow(None, "MegaMan_BattleNetwork_LegacyCollection_Vol2")

        left, top, right, bottom = win32gui.GetClientRect(hwnd)
        w = right - left
        h = bottom - top
        print(f"Client rect: {left}, {top}, {right}, {bottom}")

        hwnd_dc = win32gui.GetWindowDC(hwnd)
        mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
        save_dc = mfc_dc.CreateCompatibleDC()

        bitmap = win32ui.CreateBitmap()
        bitmap.CreateCompatibleBitmap(mfc_dc, w, h)

        WIN_HANDLES = (hwnd, hwnd_dc, mfc_dc, save_dc, bitmap)

    (hwnd, hwnd_dc, mfc_dc, save_dc, bitmap) = WIN_HANDLES
    save_dc.SelectObject(bitmap)

    # If Special K is running, this number is 3. If not, 1
    result = windll.user32.PrintWindow(hwnd, save_dc.GetSafeHdc(), 3)

    bmpinfo = bitmap.GetInfo()
    bmpstr = bitmap.GetBitmapBits(True)

    im = Image.frombuffer("RGB", (bmpinfo["bmWidth"], bmpinfo["bmHeight"]), bmpstr, "raw", "BGRX", 0, 1)

    if result != 1:
        win32gui.DeleteObject(bitmap.GetHandle())
        save_dc.DeleteDC()
        mfc_dc.DeleteDC()
        win32gui.ReleaseDC(hwnd, hwnd_dc)
        WIN_HANDLES = None
        raise RuntimeError(f"Unable to acquire screenshot! Result: {result}")


capture = capture_linux if platform.system() == "Linux" else capture_win


def run_tesseract_digits(image, top_left, text_size, invert=True):
    return int(run_tesseract(image, top_left, text_size, "--psm 6 digits", invert))


def run_tesseract_line(image, top_left, text_size, invert=True):
    return run_tesseract(image, top_left, text_size, "--psm 7", invert).strip()


def run_tesseract_word(image, top_left, text_size, invert=True):
    return run_tesseract(image, top_left, text_size, "--psm 8", invert).strip()


def run_tesseract_char(image, top_left, text_size, invert=True):
    return run_tesseract(image, top_left, text_size, "--psm 10", invert).strip()


def crop_image(image, top_left, box_size):
    start_x, start_y = top_left
    end_x = start_x + box_size[0]
    end_y = start_y + box_size[1]
    cropped = image[start_y:end_y, start_x:end_x]
    # print(os.path.join(os.path.dirname(__file__), "..", "..", "temp", "cropped.png"))
    # cv.imwrite(os.path.join(os.path.dirname(__file__), "..", "..", "temp", "cropped.png"), cropped)
    return cropped


def convert_image_to_png_bytestring(image):
    return cv.imencode(".png", image)[1].tobytes()


def scale_coords(image: Any, assumed_size: Tuple[int, int], coordinates: Tuple[int, int]) -> Tuple[int, int]:
    actual_h, actual_w, _ = image.shape
    desired_w, desired_h = assumed_size

    height_scale = actual_h / desired_h
    width_scale = actual_w / desired_w

    return round(coordinates[0] * width_scale), round(coordinates[1] * height_scale)


def run_tesseract(image, top_left, text_size, config, invert):
    scaled_top_left = scale_coords(image, (1920, 1080), top_left)
    scaled_text_size = scale_coords(image, (1920, 1080), text_size)

    roi = crop_image(image, scaled_top_left, scaled_text_size)
    gray_image = cv.cvtColor(roi, cv.COLOR_BGR2GRAY)
    _, bw_image = cv.threshold(gray_image, 30, 255, cv.THRESH_BINARY | cv.THRESH_OTSU)
    if invert:
        bw_image = cv.bitwise_not(bw_image)
    border_size = 10
    border = cv.copyMakeBorder(
        bw_image,
        top=border_size,
        bottom=border_size,
        left=border_size,
        right=border_size,
        borderType=cv.BORDER_CONSTANT,
        value=[255, 255, 255],
    )

    return pytesseract.image_to_string(border, config=config)


def crop_to_bounding_box(image, top_left, text_size, invert):
    scaled_top_left = scale_coords(image, (1920, 1080), top_left)
    scaled_text_size = scale_coords(image, (1920, 1080), text_size)

    roi = crop_image(image, scaled_top_left, scaled_text_size)
    gray_image = cv.cvtColor(roi, cv.COLOR_BGR2GRAY)
    _, bw_image = cv.threshold(gray_image, 30, 255, cv.THRESH_BINARY | cv.THRESH_OTSU)
    if not invert:
        bw_image = cv.bitwise_not(bw_image)

    contours = cv.findContours(bw_image, cv.RETR_EXTERNAL, cv.CHAIN_APPROX_SIMPLE)
    contours = contours[0] if len(contours) == 2 else contours[1]

    min_x, min_y, max_x, max_y = (sys.maxsize, sys.maxsize, 0, 0)
    for c in contours:
        x, y, w, h = cv.boundingRect(c)
        min_x = min(min_x, x)
        min_y = min(min_y, y)
        max_x = max(max_x, x + w)
        max_y = max(max_y, y + h)

    border = 10
    img_h, img_w, _ = image.shape
    min_x = max(scaled_top_left[0] + min_x - border, 0)
    min_y = max(scaled_top_left[1] + min_y - border, 0)
    max_x = min(scaled_top_left[0] + max_x + border, img_w)
    max_y = min(scaled_top_left[1] + max_y + border, img_h)

    bounded_img = crop_image(image, (min_x, min_y), (max_x - min_x, max_y - min_y))
    return bounded_img


def is_image_matching(image, template, min_x, min_y, crop_pixels=5):
    template_height, template_width, _ = template.shape
    scaled_template_w, scaled_template_h = scale_coords(image, (1920, 1080), (template_width, template_height))
    template = cv.resize(template, (scaled_template_w, scaled_template_h), interpolation=cv.INTER_AREA)
    template = template[crop_pixels : scaled_template_h - crop_pixels, crop_pixels : scaled_template_w - crop_pixels]

    template_height, template_width, _ = template.shape

    img_height, img_width, _ = image.shape
    max_x = min(min_x + template_width + 2 * crop_pixels, img_width)
    max_y = min(min_y + template_height + 2 * crop_pixels, img_height)
    min_x = max(min_x - 2 * crop_pixels, 0)
    min_y = max(min_y - 2 * crop_pixels, 0)

    cropped = image[min_y:max_y, min_x:max_x]
    return template_matching(cropped, template)


# Adapted from https://docs.opencv.org/3.4/d4/dc6/tutorial_py_template_matching.html
def template_matching(image, template):
    h, w, _ = template.shape
    img = image.copy()
    method = cv.TM_SQDIFF_NORMED
    # Apply template Matching
    res = cv.matchTemplate(img, template, method)
    min_val, max_val, min_loc, max_loc = cv.minMaxLoc(res)
    # If the method is TM_SQDIFF or TM_SQDIFF_NORMED, take minimum
    if method in [cv.TM_SQDIFF, cv.TM_SQDIFF_NORMED]:
        top_left = min_loc
    else:
        top_left = max_loc
    bottom_right = (top_left[0] + w, top_left[1] + h)

    # The tolerance has to be kinda big or else things sometimes get flaky
    return np.allclose(
        template,
        image[top_left[1] : bottom_right[1], top_left[0] : bottom_right[0]],
        rtol=3.0,
        atol=3.0,
        equal_nan=True,
    )
