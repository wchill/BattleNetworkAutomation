import cv2 as cv
import numpy as np
import os


DEMONEYE_IMG = cv.imread(os.path.join(os.path.dirname(__file__), "images", "demoneye_1345_25.png"), cv.IMREAD_COLOR)
RESULT_IMG = cv.imread(os.path.join(os.path.dirname(__file__), "images", "results_570_162.png"), cv.IMREAD_COLOR)
CHIPSELECT_IMG = cv.imread(os.path.join(os.path.dirname(__file__), "images", "chipselect_165_656.png"), cv.IMREAD_COLOR)
CUSTOM_TEXT_IMG = cv.imread(os.path.join(os.path.dirname(__file__), "images", "custom_828_1.png"), cv.IMREAD_COLOR)
CONTROLLER_IMG = cv.imread(os.path.join(os.path.dirname(__file__), "images", "controller_596_336.png"), cv.IMREAD_COLOR)


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
    return is_image_matching(image, RESULT_IMG, 570, 162)


def is_image_matching(image, template, min_x, min_y):
    template_height, template_width, _ = template.shape
    template = template[5:template_height-5, 5:template_width-5]
    template_height, template_width, _ = template.shape

    img_height, img_width, _ = image.shape
    max_x = min(min_x + template_width + 10, img_width)
    max_y = min(min_y + template_height + 10, img_height)
    min_x = max(min_x - 10, 0)
    min_y = max(min_y - 10, 0)

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
    return np.allclose(template, image[top_left[1]:bottom_right[1], top_left[0]:bottom_right[0]], rtol=3.0, atol=3.0, equal_nan=True)
