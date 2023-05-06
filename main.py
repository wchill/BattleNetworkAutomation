import sys
import time

import cv2 as cv

from bn_automation import image_processing
from bn_automation.controller import (
    Button,
    Command,
    Controller,
    DPad,
    LeftStick,
    SocketSink,
)

last_time_updated = 0

client_id = "1099988580463546408"
RPC = None


def screen_capture():
    capture = cv.VideoCapture(0)
    if not capture.isOpened():
        print("Error opening camera")
        sys.exit(1)
    _, frame = capture.read()
    cv.imwrite("frame.png", frame)
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
    for _ in range(10):
        c.press_button(Button.A)
    c.p_wait(3)


def spam_buster(c: Controller, v: cv.VideoCapture) -> None:
    while True:
        # Spam buster
        for _ in range(3):
            c.press_button(Button.B, 0.1)

        # Keep shooting until results screen pops up
        if image_processing.on_results_screen(v):
            break


def update_rpc(**kwargs):
    global last_time_updated
    if time.time() - last_time_updated > 15:
        if RPC is not None:
            RPC.update(**kwargs)
        last_time_updated = time.time()


def main_battle_loop(controller: Controller, capture: cv.VideoCapture):
    num_encounters = 0

    last_time_updated = 0
    start_time = time.time()

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
            print(f"{20 - (num_encounters % 20)} encounters before save, {num_encounters} total")
            if num_encounters % 20 == 0:
                controller.press_button(Button.Plus)
                controller.p_wait(1.0)

                zenny = image_processing.read_zenny(capture)
                bugfrags = image_processing.read_bugfrags(capture)
                print(f"Zenny: {zenny} Bugfrags: {bugfrags}")

                update_rpc(
                    large_image="bugfrag",
                    state="Grinding for BugFrags",
                    details=f"{num_encounters} battles fought, {bugfrags} BugFrags collected",
                    start=start_time,
                )

                controller.press_dpad(DPad.Up)
                controller.p_wait(0.3)
                controller.press_button(Button.A)
                controller.p_wait(0.3)
                controller.press_button(Button.A)
                controller.p_wait(0.3)
                controller.press_button(Button.A)
                controller.p_wait(0.3)
                controller.press_button(Button.B)
                controller.p_wait(0.3)
                controller.press_button(Button.B)
        elif image_processing.on_results_screen(capture):
            print("In results screen")
            results_screen(controller, capture)
        else:
            # print("In overworld")
            controller.send_cmd(Command().press(Button.B).left_value(LeftStick.Max).left_angle(LeftStick.Up).sec(0.25))
            controller.send_cmd(
                Command().press(Button.B).left_value(LeftStick.Max).left_angle(LeftStick.Down).sec(0.25)
            )


def fight_protoman_fz(controller: Controller, capture: cv.VideoCapture):
    # Dialogue
    for _ in range(3):
        print("Fighting Protoman FZ")
        controller.press_dpad(DPad.UpLeft)

        controller.press_button(Button.A)
        controller.press_button(Button.A)
        controller.press_button(Button.A)
        controller.press_button(Button.A)
        controller.press_button(Button.A)
        controller.p_wait(1.0)
        controller.press_button(Button.A)
        controller.p_wait(1.0)
        controller.press_button(Button.A)
        controller.p_wait(1.0)
        controller.press_button(Button.A)
        controller.p_wait(1.0)
        controller.press_button(Button.A)

        while not image_processing.in_battle(capture):
            controller.p_wait(0.1)

        controller.p_wait(3.0)
        print("Executing fight logic")
        other_encounter(controller, capture)

        print("Waiting for next fight iteration")
        controller.p_wait(2.0)
        controller.press_button(Button.A)
        controller.p_wait(2.0)


def buy_spreaders(controller: Controller, capture: cv.VideoCapture):
    kills = 0
    chips = 0
    num_trades_per_iteration = 8

    def update_status():
        print("Updating status")
        controller.press_button(Button.Plus)
        controller.p_wait(1.0)
        zenny = image_processing.read_zenny(capture)
        controller.press_button(Button.Plus)
        controller.p_wait(1.0)
        update_rpc(
            large_image="spreader",
            state="Grinding the chip trader",
            details=f"{kills} ProtoFZ kills, {chips} chips sacrificed, {zenny}Z",
            start=start_time,
        )
        print(f"{kills} ProtoFZ kills, {chips} chips sacrificed, {zenny}Z")
        return zenny

    zenny = update_status()

    while True:
        if zenny < num_trades_per_iteration * 600 * 10:
            print("Not enough zenny, farming Protoman FZ")
            print("Navigating to Central")
            # Go to Central
            controller.send_cmd(Command().press(Button.B).dpad(DPad.Down).sec(1))
            controller.send_cmd(Command().press(Button.B).dpad(DPad.Left).sec(3))
            controller.send_cmd()
            controller.p_wait(0.5)
            controller.press_button(Button.B)
            controller.p_wait(1.0)
            controller.press_dpad(DPad.Up)
            controller.p_wait(1.0)
            controller.press_button(Button.A)
            controller.p_wait(1.0)
            controller.press_button(Button.A)
            controller.p_wait(2.0)
            controller.press_button(Button.A)
            controller.p_wait(13.0)

            print("Navigating to Chaud")
            # Go to the school and walk next to Chaud
            controller.press_dpad(DPad.DownLeft, 0.3)
            controller.send_cmd(Command().press(Button.B).dpad(DPad.UpLeft).sec(5))
            controller.send_cmd()
            controller.send_cmd(Command().press(Button.B).dpad(DPad.Up).sec(3))
            controller.send_cmd(Command().press(Button.B).dpad(DPad.Right).sec(5))
            controller.send_cmd(Command().press(Button.B).dpad(DPad.Left).sec(1))
            controller.send_cmd(Command().press(Button.B).dpad(DPad.Up).sec(4.5))
            controller.send_cmd(Command().press(Button.B).dpad(DPad.Right).sec(1))
            controller.press_dpad(DPad.Down)
            controller.press_dpad(DPad.UpLeft, 1.5)

            while zenny < 999999:
                fight_protoman_fz(controller, capture)
                kills += 3
                zenny = update_status()

            print("Farming complete, navigating out of the school")
            # Navigate out of the school
            controller.send_cmd(Command().press(Button.B).dpad(DPad.DownRight).sec(1))
            controller.send_cmd(Command().press(Button.B).dpad(DPad.Down).sec(0.5))
            controller.send_cmd(Command().press(Button.B).dpad(DPad.Right).sec(0.5))
            controller.send_cmd(Command().press(Button.B).dpad(DPad.Down).sec(10.5))
            controller.send_cmd(Command().press(Button.B).dpad(DPad.DownRight).sec(4.5))
            controller.send_cmd(Command().press(Button.B).dpad(DPad.Right).sec(1.5))
            controller.send_cmd()
            controller.p_wait(0.5)
            controller.press_button(Button.B)
            controller.p_wait(1.0)

            print("Navigating back to chip trader")
            # Use the LevBus to go back to Green Town chip trader
            controller.press_dpad(DPad.Up)
            controller.p_wait(1.0)
            controller.press_dpad(DPad.Right)
            controller.p_wait(0.5)
            controller.press_button(Button.A)
            controller.p_wait(1.0)
            controller.press_button(Button.A)
            controller.p_wait(2.0)
            controller.press_button(Button.A)
            controller.p_wait(13.0)
            controller.send_cmd(Command().press(Button.B).dpad(DPad.Right).sec(3.5))

        print("Restocking chips, navigating to shop")
        # Get to the courthouse
        controller.send_cmd(Command().press(Button.B).dpad(DPad.Right).sec(1))
        controller.send_cmd(Command().press(Button.B).dpad(DPad.Down).sec(3))
        controller.send_cmd(Command().press(Button.B).dpad(DPad.Right).sec(3))
        controller.send_cmd(Command().press(Button.B).dpad(DPad.Up).sec(3))
        controller.send_cmd(Command().dpad(DPad.Left).sec(1))
        controller.send_cmd(Command().dpad(DPad.Down).sec(1))

        # Jack in
        controller.press_button(Button.R)
        controller.p_wait(7.5)

        # Navigate to Lan's HP
        controller.send_cmd(Command().press(Button.B).dpad(DPad.Up).sec(0.1))
        controller.send_cmd()
        controller.p_wait(2.0)

        # Navigate to CentralArea1
        controller.send_cmd(Command().dpad(DPad.Up).sec(0.2))
        controller.send_cmd()
        controller.send_cmd(Command().press(Button.B).dpad(DPad.UpRight).sec(0.1))
        controller.send_cmd()
        controller.p_wait(2.0)

        # Navigate to CentralArea2
        controller.send_cmd(Command().press(Button.B).dpad(DPad.UpRight).sec(0.1))
        controller.send_cmd()
        controller.p_wait(0.8)
        controller.send_cmd(Command().press(Button.B).dpad(DPad.Down).sec(0.1))
        controller.send_cmd()
        controller.p_wait(0.5)
        controller.send_cmd(Command().press(Button.B).dpad(DPad.Right).sec(0.1))
        controller.send_cmd()
        controller.p_wait(0.5)
        controller.send_cmd(Command().press(Button.B).dpad(DPad.Down).sec(0.1))
        controller.send_cmd()
        controller.p_wait(0.5)
        controller.send_cmd(Command().press(Button.B).dpad(DPad.Right).sec(0.1))
        controller.send_cmd()
        controller.p_wait(0.5)
        controller.send_cmd(Command().press(Button.B).dpad(DPad.UpRight).sec(0.1))
        controller.send_cmd()
        controller.p_wait(1.2)
        controller.send_cmd(Command().press(Button.B).dpad(DPad.UpLeft).sec(0.1))
        controller.send_cmd()
        controller.p_wait(1.2)
        controller.send_cmd(Command().press(Button.B).dpad(DPad.UpRight).sec(0.1))
        controller.send_cmd()
        controller.p_wait(1.2)
        controller.send_cmd(Command().press(Button.B).dpad(DPad.Right).sec(1))
        controller.send_cmd()
        controller.send_cmd(Command().press(Button.B).dpad(DPad.Up).sec(2.0))
        controller.send_cmd()
        controller.p_wait(0.5)

        print("Buying chips")
        # Talk to the trader
        controller.send_cmd(Command().press(Button.B).dpad(DPad.UpRight).sec(0.1))
        controller.send_cmd()
        controller.p_wait(0.8)

        controller.press_button(Button.A)
        controller.press_button(Button.A)
        controller.press_button(Button.A)
        controller.p_wait(1)

        # Buy 99 Spreader L
        for _ in range(num_trades_per_iteration * 10 * 3):
            controller.press_button(Button.A, 0.15)

        # Exit menus
        controller.press_button(Button.B)
        controller.press_button(Button.B)
        controller.press_button(Button.B)
        controller.press_button(Button.B)
        controller.p_wait(1.0)

        print("Navigating back to chip trader")
        # Jack out
        controller.press_button(Button.R)
        controller.p_wait(1.0)
        controller.press_dpad(DPad.Left, 0.1)
        controller.p_wait(0.5)
        controller.press_button(Button.A)
        controller.press_button(Button.A)
        controller.press_button(Button.A)
        controller.p_wait(2.0)

        # Exit courthouse
        controller.send_cmd(Command().dpad(DPad.Right).sec(1))
        controller.send_cmd(Command().press(Button.B).dpad(DPad.Down).sec(1))
        controller.send_cmd()
        controller.send_cmd(Command().press(Button.B).dpad(DPad.Left).sec(8))
        controller.send_cmd()
        controller.send_cmd(Command().press(Button.B).dpad(DPad.UpRight).sec(1))
        controller.send_cmd()
        controller.send_cmd(Command().press(Button.B).dpad(DPad.Right).sec(3))
        controller.send_cmd()
        controller.press_dpad(DPad.Up)

        print("Using chip trader")
        # Use chip trader
        controller.press_button(Button.A)
        controller.p_wait(2.0)

        controller.press_button(Button.A)
        controller.p_wait(1.0)

        # Do the chip trades
        for _ in range(num_trades_per_iteration):
            for _ in range(10):
                controller.press_button(Button.A, 0.15)
            for _ in range(8):
                controller.press_button(Button.A, 0.2)
            controller.p_wait(1.0)
            chips += 10

        # Exit chip trader and check zenny to see if we need to farm protoman again
        controller.press_button(Button.B)
        controller.p_wait(1.0)
        controller.press_button(Button.B)

        controller.p_wait(2.0)
        zenny = update_status()


if __name__ == "__main__":
    capture = cv.VideoCapture(0)
    if not capture.isOpened():
        print("Error opening camera")
        sys.exit(1)

    with SocketSink("raspberrypi.local", 3000) as sink:
        controller = Controller(sink)

        try:
            from pypresence import Presence

            RPC = Presence(client_id=client_id)
            RPC.connect()
        except Exception:
            pass

        start_time = time.time()

        # main_battle_loop(controller, capture)
        buy_spreaders(controller, capture)
