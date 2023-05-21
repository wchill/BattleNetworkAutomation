import collections
import errno
import getpass
import inspect
import logging
import signal
import socket
import threading
import time
from typing import Callable, Optional, Tuple

import functionfs
from functionfs.gadget import ConfigFunctionFFSSubprocess, GadgetSubprocessManager

from . import gamepad_input
from .commands import ControllerRequest, ControllerResponse
from .raw_inputs import (
    EMPTY_REPORT,
    RawButton,
    RawDPad,
    RawLeftStick,
    RawRightStick,
    _RawDPad,
)

logger = logging.getLogger(__name__)

"""
0x05, 0x01,        // Usage Page (Generic Desktop Ctrls)
0x09, 0x05,        // Usage (Game Pad)
0xA1, 0x01,        // Collection (Application)
0x15, 0x00,        //   Logical Minimum (0)
0x25, 0x01,        //   Logical Maximum (1)
0x35, 0x00,        //   Physical Minimum (0)
0x45, 0x01,        //   Physical Maximum (1)
0x75, 0x01,        //   Report Size (1)
0x95, 0x0E,        //   Report Count (14)
0x05, 0x09,        //   Usage Page (Button)
0x19, 0x01,        //   Usage Minimum (0x01)
0x29, 0x0E,        //   Usage Maximum (0x0E)
0x81, 0x02,        //   Input (Data,Var,Abs,No Wrap,Linear,Preferred State,No Null Position)
0x95, 0x02,        //   Report Count (2)
0x81, 0x01,        //   Input (Const,Array,Abs,No Wrap,Linear,Preferred State,No Null Position)
0x05, 0x01,        //   Usage Page (Generic Desktop Ctrls)
0x25, 0x07,        //   Logical Maximum (7)
0x46, 0x3B, 0x01,  //   Physical Maximum (315)
0x75, 0x04,        //   Report Size (4)
0x95, 0x01,        //   Report Count (1)
0x65, 0x14,        //   Unit (System: English Rotation, Length: Centimeter)
0x09, 0x39,        //   Usage (Hat switch)
0x81, 0x42,        //   Input (Data,Var,Abs,No Wrap,Linear,Preferred State,Null State)
0x65, 0x00,        //   Unit (None)
0x95, 0x01,        //   Report Count (1)
0x81, 0x01,        //   Input (Const,Array,Abs,No Wrap,Linear,Preferred State,No Null Position)
0x26, 0xFF, 0x00,  //   Logical Maximum (255)
0x46, 0xFF, 0x00,  //   Physical Maximum (255)
0x09, 0x30,        //   Usage (X)
0x09, 0x31,        //   Usage (Y)
0x09, 0x32,        //   Usage (Z)
0x09, 0x35,        //   Usage (Rz)
0x75, 0x08,        //   Report Size (8)
0x95, 0x04,        //   Report Count (4)
0x81, 0x02,        //   Input (Data,Var,Abs,No Wrap,Linear,Preferred State,No Null Position)
0x75, 0x08,        //   Report Size (8)
0x95, 0x01,        //   Report Count (1)
0x81, 0x01,        //   Input (Const,Array,Abs,No Wrap,Linear,Preferred State,No Null Position)
0xC0,              // End Collection
// 80 bytes
"""

REPORT_DESCRIPTOR = (
    b"\x05\x01\t\x05\xa1\x01\x15\x00%\x015\x00E\x01u\x01\x95\x0e\x05\t\x19\x01)\x0e\x81\x02\x95\x02"
    b"\x81\x01\x05\x01%\x07F;\x01u\x04\x95\x01e\x14\t9\x81Be\x00\x95\x01\x81\x01&\xff\x00F\xff\x00\t0"
    b"\t1\t2\t5u\x08\x95\x04\x81\x02u\x08\x95\x01\x81\x01\xc0 "
)


def print_func_name_and_args():
    stack_frame = inspect.stack()[1]
    func = stack_frame.function
    frame = stack_frame.frame
    args, args_paramname, kwargs_paramname, values = inspect.getargvalues(frame)
    arg_str = ",".join(f"{arg}={values[arg]}" for arg in args)
    print(f"{func}({arg_str})")


class HIDInEndpoint(functionfs.EndpointINFile):
    """
    Customise what happens on IN transfer completion.
    In a real device, here may be where you would sample and clear the current
    movement deltas, and construct a new HID report to send to the host.
    """

    def __init__(self, path, submit, eventfd):
        super().__init__(path, submit, eventfd)
        self.report_callback: Optional[Callable[..., bytes]] = None

    def set_report_callback(self, callback: Callable[..., bytes]) -> None:
        self.report_callback = callback

    def onComplete(self, buffer_list, user_data, status):
        if status < 0:
            if status == -errno.ESHUTDOWN:
                # Unplugged, host selected another configuration, ...
                # Stop submitting the transfer.
                return False
            raise IOError(-status)

        # Resubmit the transfer with a new report.
        report = self.report_callback() if self.report_callback is not None else EMPTY_REPORT
        return [bytearray(report)]


class HIDOutEndpoint(functionfs.EndpointOUTFile):
    def onComplete(self, data, status):
        """
        Called when this endpoint received data.
        data (memoryview, None)
            Data received, or None if there was an error.
            Once this method returns the underlying buffer will be reused,
            so you must copy any piece you cannot immediately process.
        status (int, None)
            Error code if there was an error (negative errno value), zero
            otherwise.
        May be overridden in subclass.
        """
        if status < 0:
            print(f"Error in OUT endpoint: errno {-status}")
        else:
            print(f"Got report from OUT endpoint: {data}")


class UsbHidDevice(functionfs.HIDFunction):
    """
    A simple USB HID device.
    """

    def __init__(
        self,
        path,
        descriptor_dict=(),
        fs_list=(),
        hs_list=(),
        ss_list=(),
        os_list=(),
        lang_dict=(),
        all_ctrl_recip=False,
        config0_setup=False,
        is_boot_device=False,
        protocol=functionfs.USB_INTERFACE_PROTOCOL_NONE,
        country_code=0,
        in_report_max_length=64,
        out_report_max_length=64,
        full_speed_interval=1,
        high_speed_interval=4,
    ):
        """
        path, ss_list, os_list, lang_dict, all_ctrl_recip, config0_setup
            See Function.__init__ .
        fs_list, hs_list:
            If provided, these values are used instead of automatically
            generating minimal valid descriptors, with IN endpoint at index 1
            and OUT endpoint (if out_report_max_length is non-zero) at
            index 2.
        report_descriptor (bytes)
            The report descriptor. Describes the structure of all reports
            the interface may generate.
        hid_descriptor_list (dict)
            keys (int)
                hid.HID_DT_* values
                Note: hid.HID_DT_REPORT descriptor should rather be provided
                using report_descriptor argument (see above).
            values (list of bytes)
                List of descriptors of this type.
                Note for hid.HID_DT_PHYSICAL: descriptor 0 (see HID 1.11,
                6.2.3) will not be automatically generated.
        All other arguments are for automated descriptor generation, and are
        ignored when fs_list and hs_list are non-empty:
        is_boot_device (bool)
            Whether this interface implements boot device protocol.
        protocol (USB_INTERFACE_PROTOCOL_*)
            Should be provided when is_boot_device is True.
        country_code (int)
            The country code this interface is localised for.
            See table in HID 1.11 specification, 6.2.1 .
        in_report_max_length (int)
            Must be greater than zero to auto-generate a valid descriptor.
            The length of the longest report this interface will produce,
            in bytes.
            If >64 bytes, the devide will be high-speed only.
        out_report_max_length (int)
            If zero, this interface will not have an interrupt OUT endpoint
            (only interrupt IN).
            Otherwise, this is the length of the longest report this interface
            can receive, in bytes.
            If >64 bytes, the devide will be high-speed only.
        full_speed_interval (int)
            Interval for polling endpoint for data transfers.
            In milliseconds units, 1 to 255.
        high_speed_interval (int)
            Interval for polling endpoint for data transfers.
            In 2 ** (n - 1) * 125 microseconds units, 1 to 16:
             1:     125 microseconds
             2:     250
             3:     500
             4:    1000
             5:    2000
             6:    4000
             7:    8000
             8:   16000
             9:   32000
            10:   64000
            11:  128000
            12:  256000
            13:  512000
            14: 1024000
            15: 2048000
            16: 4096000
        """
        super().__init__(
            path=path,
            report_descriptor=REPORT_DESCRIPTOR,
            descriptor_dict=descriptor_dict,
            fs_list=fs_list,
            hs_list=hs_list,
            ss_list=ss_list,
            os_list=os_list,
            lang_dict=lang_dict,
            all_ctrl_recip=all_ctrl_recip,
            config0_setup=config0_setup,
            is_boot_device=is_boot_device,
            protocol=protocol,
            country_code=country_code,
            in_report_max_length=in_report_max_length,
            out_report_max_length=out_report_max_length,
            full_speed_interval=full_speed_interval,
            high_speed_interval=high_speed_interval,
        )
        self._joystick_lock = threading.RLock()
        self._user_override_cv = threading.Condition()
        self._gamepad_connected_cv = threading.Condition()
        self.using_gamepad = False

        self.gamepad_state = RawButton.Nothing + RawDPad.Center + RawLeftStick.Center + RawRightStick.Center
        self.dpad_state = [0, 0]

        self.report_queue: collections.deque[Tuple[bytes, Optional[int]]] = collections.deque()
        self.current_report: Tuple[bytes, Optional[int]] = (EMPTY_REPORT, None)

        self.joystick_thread = threading.Thread(target=self.handle_joystick, args=(), daemon=True)
        self.joystick_thread.start()

        self.server_thread = threading.Thread(target=self.listen_on_socket, args=(), daemon=True)
        self.server_thread.start()
        self.enabled = False

    def get_report(self) -> bytes:
        if self.current_report[1] is None:
            if len(self.report_queue) == 0:
                # Current report with infinite repeat and nothing in queue, return report
                return self.current_report[0]
            else:
                # Current report with infinite repeat and something in queue, process queue
                self.current_report = self.report_queue.popleft()
                # print(self.current_report)
        elif self.current_report[1] < 0:
            if len(self.report_queue) == 0:
                # Current report with no repeats remaining and nothing in queue, use empty report
                self.current_report = (EMPTY_REPORT, None)
                # print(self.current_report)
            else:
                # Current report with no repeats remaining and something in queue, process queue
                self.current_report = self.report_queue.popleft()
                # print(self.current_report)

        # Process report, decrement by 1 if not infinitely repeating
        report, times = self.current_report
        self.current_report = (report, times - 1 if times is not None else times)
        return report

    def add_report_to_queue(self, report: bytes, num_repeats: Optional[int] = 0) -> None:
        self.report_queue.append((report, num_repeats))

    @staticmethod
    def send_response(conn: socket.socket, response_header: ControllerResponse, response_body: bytes = b"") -> int:
        data = response_header.to_bytes(1, byteorder="little", signed=False) + response_body
        return conn.send(data)

    @staticmethod
    def interpret_command(command: bytes) -> Tuple[ControllerRequest, int]:
        if len(command) != 1:
            raise ValueError(f"Command should be exactly 1 byte: {command}")
        request_int = int.from_bytes(command, byteorder="little", signed=False)
        request = ControllerRequest(request_int)

        # Specify how many more bytes are expected
        if request == ControllerRequest.UPDATE_REPORT:
            return request, 8
        elif request == ControllerRequest.UPDATE_REPORT_N_TIMES:
            return request, 10
        else:
            return request, 0

    def handle_joystick(self):
        while True:
            with self._gamepad_connected_cv:
                gamepad_input.monitor_gamepads(self._gamepad_connected_cv)
                if len(gamepad_input.available_gamepads) == 0:
                    print("Gamepad not connected, waiting for gamepad connection")
                self._gamepad_connected_cv.wait_for(lambda: len(gamepad_input.available_gamepads) > 0)
            try:
                print("Gamepad connected, processing inputs")
                active_device = list(gamepad_input.available_gamepads.values())[0]
                active_device.handle_button_changed_callback = self.handle_button_changed
                active_device.handle_axis_changed_callback = self.handle_axis_changed
                active_device.process_updates()
            except IndexError:
                # Could happen due to race condition
                continue

    def handle_button_changed(self, button: str, is_pressed: bool):
        if button == "Home":
            if not is_pressed:
                with self._joystick_lock:
                    self.report_queue.clear()
                    self.using_gamepad = not self.using_gamepad
                    print(f"Using gamepad: {self.using_gamepad}")
                    if not self.using_gamepad:
                        with self._user_override_cv:
                            self._user_override_cv.notify()
        else:
            if is_pressed:
                self.gamepad_state |= RawButton[button]
            else:
                self.gamepad_state &= ~RawButton[button]

            with self._joystick_lock:
                if self.using_gamepad:
                    report = self.gamepad_state.to_bytes(8, byteorder="little")
                    self.current_report = report, None

    def handle_axis_changed(self, axis: str, position: float):
        if axis == "ZL" or axis == "ZR":
            if position < 0:
                self.gamepad_state &= ~RawButton[axis]
            else:
                self.gamepad_state |= RawButton[axis]
        elif axis.startswith("DPAD"):
            index = 0 if axis.endswith("X") else 1
            self.dpad_state[index] = int(position)
            dpad_tuple = self.dpad_state[0], self.dpad_state[1]
            lookup_table = {
                (-1, -1): RawDPad.UpLeft,
                (-1, 0): RawDPad.Left,
                (-1, 1): RawDPad.DownLeft,
                (0, -1): RawDPad.Up,
                (0, 0): RawDPad.Center,
                (0, 1): RawDPad.Down,
                (1, -1): RawDPad.UpRight,
                (1, 0): RawDPad.Right,
                (1, 1): RawDPad.DownRight,
            }
            self.gamepad_state &= ~(0xFF << _RawDPad.SHIFT_BITS)
            self.gamepad_state |= lookup_table[dpad_tuple]
        else:
            stick = RawLeftStick if axis.startswith("LEFT") else RawRightStick
            shift_bits = stick.SHIFT_BITS
            if axis.endswith("Y"):
                shift_bits += 8

            int_pos = min(max(int(position * 256 + 128.5), 0), 255)
            self.gamepad_state &= ~(0xFF << shift_bits)
            self.gamepad_state |= int_pos << shift_bits

        with self._joystick_lock:
            if self.using_gamepad:
                report = self.gamepad_state.to_bytes(8, byteorder="little")
                self.current_report = report, None

    def listen_on_socket(self):
        sock = socket.socket()
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("0.0.0.0", 3000))
        sock.listen(1)

        should_stop = False
        try:
            while not should_stop:
                try:
                    conn, addr = sock.accept()
                    print(f"Accepting socket connection from {addr}: {conn}")
                    while not self.enabled:
                        time.sleep(0.1)
                    print(f"USB host enabled endpoint, unblocking client")
                    self.send_response(conn, ControllerResponse.HOST_ENABLED)

                    while True:
                        command = conn.recv(1)
                        if not command:
                            print("Exiting loop because of EOF")
                            conn.close()
                            break

                        request, num_bytes_needed = self.interpret_command(command)

                        bytes_recv = 0
                        msg = b""
                        while bytes_recv < num_bytes_needed:
                            msg += conn.recv(num_bytes_needed - bytes_recv)
                            bytes_recv = len(msg)
                            if not msg:
                                conn.close()

                        if (
                            request == ControllerRequest.UPDATE_REPORT
                            or request == ControllerRequest.UPDATE_REPORT_N_TIMES
                        ):
                            self._joystick_lock.acquire()
                            if self.using_gamepad:
                                self._joystick_lock.release()
                                print("Blocking client since user requested direct controller input")
                                self.send_response(conn, ControllerResponse.USER_OVERRIDE)
                                with self._user_override_cv:
                                    while self.using_gamepad:
                                        self._user_override_cv.wait()
                                print("Unblocking client since user disabled direct controller input")
                                self.send_response(conn, ControllerResponse.HOST_ENABLED)
                            else:
                                if len(msg) > 8:
                                    repeat_times = int.from_bytes(msg[8:10], byteorder="little")
                                else:
                                    repeat_times = None
                                self.add_report_to_queue(msg, repeat_times)
                                self._joystick_lock.release()
                                self.send_response(conn, ControllerResponse.ACK)
                        elif request == ControllerRequest.STOP:
                            print(f"Stop requested")
                            should_stop = True
                            signal.raise_signal(signal.SIGINT)
                            break
                except ConnectionResetError:
                    pass
        finally:
            sock.close()

    def getEndpointClass(self, is_in, descriptor):
        """
        Tall HIDFunction that we want it to use our custom IN endpoint class
        for our only IN endpoint.
        """
        return HIDInEndpoint if is_in else HIDOutEndpoint

    def onEnable(self):
        """
        We are plugged to a host, it has enumerated and enabled us, start
        sending reports.
        """
        print("onEnable called")
        super().onEnable()
        self.enabled = True
        in_endpoint: HIDInEndpoint = self.getEndpoint(1)
        in_endpoint.set_report_callback(self.get_report)
        in_endpoint.submit((bytearray(EMPTY_REPORT),))

    def setInterfaceDescriptor(self, value, index, length):
        """
        May be overriden and implemented in subclass.
        Return if request was handled,
        Call method on superclass (this class) otherwise so error is signaled
        to host.
        """
        print_func_name_and_args()
        super().setInterfaceDescriptor(value, index, length)

    def getHIDReport(self, value, index, length):
        """
        Must be overridden and implemented in subclass.
        Return if request was handled,
        Call method on superclass (this class) otherwise so error is signaled
        to host.
        """
        print("getHIDReport()")
        self.ep0.write(self.get_report())

    def getHIDIdle(self, value, index, length):
        """
        May be overridden and implemented in subclass.
        Return if request was handled,
        Call method on superclass (this class) otherwise so error is signaled
        to host.
        """
        print_func_name_and_args()
        super().getHIDIdle(value, index, length)

    def getHIDProtocol(self, value, index, length):
        """
        May be overridden and implemented in subclass.
        Mandatory for boot devices.
        Return if request was handled,
        Call method on superclass (this class) otherwise so error is signaled
        to host.
        """
        print_func_name_and_args()
        super().getHIDProtocol(value, index, length)

    def setHIDReport(self, value, index, length):
        """
        May be overridden and implemented in subclass.
        Return if request was handled,
        Call method on superclass (this class) otherwise so error is signaled
        to host.
        """
        print_func_name_and_args()
        super().setHIDReport(value, index, length)

    def setHIDIdle(self, value, index, length):
        """
        May be overridden and implemented in subclass.
        Return if request was handled,
        Call method on superclass (this class) otherwise so error is signaled
        to host.
        """
        print_func_name_and_args()
        super().setHIDIdle(value, index, length)

    def setHIDProtocol(self, value, index, length):
        """
        May be overridden and implemented in subclass.
        Mandatory for boot devices.
        Return if request was handled,
        Call method on superclass (this class) otherwise so error is signaled
        to host.
        """
        print_func_name_and_args()
        super().setHIDProtocol(value, index, length)


_subprocess_manager = None
_lock = threading.Lock()


def subprocess_manager():
    with _lock:
        global _subprocess_manager
        if _subprocess_manager is None:
            args = GadgetSubprocessManager.getArgumentParser().parse_args(["--username", getpass.getuser()])
            _subprocess_manager = GadgetSubprocessManager(
                args=args,
                config_list=[
                    # A single configuration
                    {
                        "function_list": [
                            get_config_function_subprocess,
                        ],
                        "MaxPower": 500,
                        "lang_dict": {
                            0x409: {},
                        },
                    }
                ],
                idVendor=0x0F0D,  # HORI CO., LTD.
                idProduct=0x00C1,  # HORIPAD S
                bcdDevice=0x0572,
                lang_dict={
                    0x409: {
                        "product": "HORIPAD S",
                        "manufacturer": "HORI CO.,LTD.",
                    },
                },
                name="usbhid",
            )
        return _subprocess_manager


def get_config_function_subprocess(**kwargs):
    return ConfigFunctionFFSSubprocess(getFunction=UsbHidDevice, **kwargs)
