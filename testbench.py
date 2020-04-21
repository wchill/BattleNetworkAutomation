from controller import Controller, Command, DPad, Button, LeftStick, RightStick
from sinks import SocketSink, UsbHidGadgetSink

WAIT_TIME = 0.1
WAIT_TIME_2 = 0.2


class TestBench:

    def __init__(self, controller: Controller):
        self.controller = controller
    
    def testbench_btn(self):
        for button in sorted(set(Button.All()) - {Button.Capture, Button.Home, Button.Nothing}):
            print(f"Testing: {repr(Button(button))}")
            self.controller.send_cmd(Command().press(button))
            self.controller.p_wait(WAIT_TIME)
            self.controller.send_cmd()
            self.controller.p_wait(WAIT_TIME_2)

    # Test DPAD
    def testbench_dpad(self):
        for dpad in DPad.All():
            print(f"Testing: {repr(DPad(dpad))}")
            self.controller.send_cmd(Command().dpad(dpad))
            self.controller.p_wait(WAIT_TIME)
            self.controller.send_cmd()
            self.controller.p_wait(WAIT_TIME_2)

    # Test Analog Sticks
    def testbench_sticks(self):
        for Stick in [LeftStick, RightStick]:
            # Test U/R/D/L
            for angle in Stick.Directions:
                self.controller.send_cmd(Command().stick_angle(Stick.angle(angle)).stick_value(Stick.intensity(Stick.Max)))
                self.controller.p_wait(WAIT_TIME)

            # 360 Circle @ Full/Partial intensity
            for intensity in [Stick.Max, Stick.Half]:
                for i in range(360):
                    cmd = Command().stick_angle(Stick.angle(i + 90)).stick_value(Stick.intensity(intensity))
                    self.controller.send_cmd(cmd)
                    self.controller.p_wait(0.01)
                self.controller.send_cmd()
                self.controller.p_wait(WAIT_TIME)

    def run(self):
        # self.testbench_btn()
        # self.controller.send_cmd()
        # self.controller.p_wait(WAIT_TIME_2)
        # self.testbench_dpad()
        # self.controller.send_cmd()
        # self.controller.p_wait(WAIT_TIME_2)
        self.testbench_sticks()
        self.controller.send_cmd()
        self.controller.p_wait(WAIT_TIME)


if __name__ == "__main__":
    with SocketSink('127.0.0.1', 3000) as sink:
        c = Controller(sink)
        testbench = TestBench(c)
        testbench.run()
