import select
from threading import Thread

from sinks import ControllerSink


class UsbHidGadgetSink(ControllerSink):
    def __init__(self, device: str = "/dev/hidg0"):
        self.device = None
        self.device_path = device
        self.recv_thread = Thread(target=self.process_reports, args=(self,))

    def __enter__(self):
        self.device = open(self.device_path, "r+b")
        # self.recv_thread.start()
        return self.device

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.device is not None:
            self.device.close()
            self.device = None

    def process_reports(self):
        while self.device is not None:
            try:
                r_read, r_write, r_except = select.select([self.device], [], [])
                data = self.device.read()
                print("recv report: " + data)
            except Exception:
                import traceback
                traceback.print_exc()
