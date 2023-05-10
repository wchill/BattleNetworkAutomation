import os
import sys
from typing import Any, Tuple

import cv2 as cv
import numpy as np
import pytesseract
from pytesseract import Output

DEMONEYE_IMG = cv.imread(os.path.join(os.path.dirname(__file__), "images", "demoneye_1345_25.png"), cv.IMREAD_COLOR)
RESULT_IMG = cv.imread(os.path.join(os.path.dirname(__file__), "images", "results_365_120.png"), cv.IMREAD_COLOR)
CHIPSELECT_IMG = cv.imread(os.path.join(os.path.dirname(__file__), "images", "chipselect_165_656.png"), cv.IMREAD_COLOR)
CUSTOM_TEXT_IMG = cv.imread(os.path.join(os.path.dirname(__file__), "images", "custom_828_1.png"), cv.IMREAD_COLOR)
CONTROLLER_IMG = cv.imread(os.path.join(os.path.dirname(__file__), "images", "controller_596_336.png"), cv.IMREAD_COLOR)


CAPTURE = None


def capture():
    global CAPTURE
    if CAPTURE is None:
        CAPTURE = cv.VideoCapture(0)
    return CAPTURE.read()[1]


def read_zenny(capture: cv.VideoCapture) -> int:
    top_left = (1110, 400)
    text_size = (450, 85)
    _, image = capture.read()
    res = run_tesseract_digits(image, top_left, text_size)
    return int(res)


def read_bugfrags(capture: cv.VideoCapture) -> int:
    top_left = (1110, 562)
    text_size = (500, 85)
    _, image = capture.read()
    res = run_tesseract_digits(image, top_left, text_size)
    return int(res)


def run_tesseract_digits(image, top_left, text_size, invert=True):
    try:
        return int(run_tesseract(image, top_left, text_size, "--psm 6 digits", invert))
    except ValueError:
        start_x, start_y = top_left
        end_x = start_x + text_size[0]
        end_y = start_y + text_size[1]
        roi = image[start_y:end_y, start_x:end_x]
        gray_image = cv.cvtColor(roi, cv.COLOR_BGR2GRAY)
        _, bw_image = cv.threshold(gray_image, 30, 255, cv.THRESH_BINARY | cv.THRESH_OTSU)
        bw_image = cv.bitwise_not(bw_image)
        cv.imshow("error", bw_image)
        cv.waitKey()


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
    return image[start_y:end_y, start_x:end_x]


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


def on_controller_screen(capture: cv.VideoCapture) -> bool:
    _, image = capture.read()
    return is_image_matching(image, CONTROLLER_IMG, 596, 336)


def in_battle(capture: cv.VideoCapture) -> bool:
    _, image = capture.read()
    return is_image_matching(image, CHIPSELECT_IMG, 165, 656) or is_image_matching(image, CUSTOM_TEXT_IMG, 828, 1)


def in_demoneye_battle(capture: cv.VideoCapture) -> bool:
    _, image = capture.read()
    return is_image_matching(image, DEMONEYE_IMG, 1345, 25)


def on_results_screen(capture: cv.VideoCapture) -> bool:
    _, image = capture.read()
    return is_image_matching(image, RESULT_IMG, 365, 120)


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
