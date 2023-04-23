import cv2 as cv
import sys

import image_processing
from controller import Command, Controller, Button, DPad, LeftStick, RightStick
from sinks import SocketSink


"""
def reset_controller(ctrl=None):
    if ctrl is None:
        ctrl = controller.Controller('COM6')

    ctrl.press_button(controller.BTN_B)

    ctrl.press_button(controller.BTN_HOME)
    ctrl.p_wait(1)
    ctrl.press_button(controller.DPAD_D)
    ctrl.press_button(controller.DPAD_R)
    ctrl.press_button(controller.DPAD_R)
    ctrl.press_button(controller.DPAD_R)
    ctrl.press_button(controller.BTN_A)
    ctrl.p_wait(1)
    ctrl.press_button(controller.BTN_A)
    return ctrl
"""


def screen_capture():
    capture = cv.VideoCapture(0)
    if not capture.isOpened():
        print('Error opening camera')
        sys.exit(1)
    _, frame = capture.read()
    cv.imwrite('frame.png', frame)
    capture.release()
    sys.exit()


def sensor_encounter(c: Controller, v: cv.VideoCapture) -> None:
    # Select regular chip + close custom window
    c.press_button(Button.A)
    c.press_button(Button.Plus)
    c.press_button(Button.A)

    # Wait for battle start
    c.p_wait(2.0)

    # Use chip
    c.press_button(Button.A)

    # Wait for results screen
    c.p_wait(3.0)

    # In case we get stuck, fire the buster a bunch of times
    spam_buster(c, v)
    results_screen(c, v)


def other_encounter(c: Controller, v: cv.VideoCapture) -> None:
    # Close custom window
    c.press_button(Button.Plus)
    c.press_button(Button.A)

    spam_buster(c, v)
    results_screen(c, v)


def connect_controller(c: Controller, v: cv.VideoCapture) -> None:
    # Controller screen
    c.press_button(Button.L | Button.R)
    c.p_wait(2.0)
    c.press_button(Button.A)

    # Wait for Minus menu
    c.p_wait(2.0)

    # Exit menu
    c.press_button(Button.B)
    c.p_wait(2.0)


def results_screen(c: Controller, v: cv.VideoCapture) -> None:
    # Continually press A while results screen visible
    while True:
        c.press_button(Button.A)
        if not image_processing.on_results_screen(v):
            break

    # Wait for overworld loop
    c.p_wait(1.5)


def spam_buster(c: Controller, v: cv.VideoCapture) -> None:
    while True:
        # Keep shooting until results screen pops up
        if image_processing.on_results_screen(v):
            break

        # Spam buster
        for _ in range(3):
            c.press_button(Button.B, 0.1)


def save(c: Controller, v:cv.VideoCapture) -> None:
    c.press_button(Button.Plus)
    c.p_wait(0.3)
    c.press_dpad(DPad.Up)
    c.p_wait(0.3)
    c.press_button(Button.A)
    c.p_wait(0.3)
    c.press_button(Button.A)
    c.p_wait(0.3)
    c.press_button(Button.A)
    c.p_wait(0.3)
    c.press_button(Button.B)
    c.p_wait(0.3)
    c.press_button(Button.B)


def main_battle_loop(controller: Controller, capture: cv.VideoCapture):
    num_encounters = 0

    while True:
        if image_processing.in_battle(capture):
            controller.p_wait(3.0)
            # Reset cross selection if it pops up
            controller.press_button(Button.B)

            if image_processing.in_demoneye_battle(capture):
                print("In sensor encounter")
                sensor_encounter(controller, capture)
            else:
                print("In other encounter")
                other_encounter(controller, capture)
            num_encounters += 1
            if num_encounters % 20 == 0:
                save(controller, capture)
        elif image_processing.on_results_screen(capture):
            print("In results screen")
            results_screen(controller, capture)
        else:
            print("In overworld")
            controller.send_cmd(Command().press(Button.B).left_value(LeftStick.Max).left_angle(LeftStick.Up).sec(0.25))
            controller.send_cmd(
                Command().press(Button.B).left_value(LeftStick.Max).left_angle(LeftStick.Down).sec(0.25))


def buy_spreaders(controller: Controller, capture: cv.VideoCapture):
    while True:
        controller.press_button(Button.A)


if __name__ == '__main__':
    capture = cv.VideoCapture(0)
    if not capture.isOpened():
        print('Error opening camera')
        sys.exit(1)

    with SocketSink("raspberrypi.local", 3000) as sink:
        controller = Controller(sink)

        # connect_controller(controller, capture)
        # controller.press_button(Button.B)
        # controller.press_button(Button.B)

        buy_spreaders(controller, capture)
