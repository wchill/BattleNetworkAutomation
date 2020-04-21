from sinks.controller_sink import ControllerSink
from utils.crc8_wrapper import Crc8WrappedFileLikeObject


class SerialPortSink(ControllerSink):
    def __init__(self, serial_port: str = "/dev/ttyAMA0", baudrate: int = 19200):
        self.port_name = serial_port
        self.baudrate = baudrate
        self.port = None

    def __enter__(self):
        import serial
        self.port = serial.Serial(port=self.port_name, baudrate=self.baudrate, timeout=1)
        return Crc8WrappedFileLikeObject(self.port)

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.port is not None:
            self.port.close()
            self.port = None
