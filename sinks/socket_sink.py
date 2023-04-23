import ipaddress
import socket
import time

from . import ControllerSink
from utils.structs import FuncFsServerRequest, FuncFsServerResponse


class SocketSink(ControllerSink):
    @staticmethod
    def get_ip_from_hostname(hostname: str) -> str:
        return socket.gethostbyname(hostname)

    def __init__(self, ip_or_host: str, port: int):
        try:
            ipaddress.ip_address(ip_or_host)
        except ValueError:
            ip_or_host = self.get_ip_from_hostname(ip_or_host)

        self.sock = None
        self.ip = ip_or_host
        self.port = port

    def __enter__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((self.ip, self.port))

        # wait for connection
        while True:
            msg = FuncFsServerResponse.from_bytes(self.sock.recv(1), byteorder='little')
            if msg == FuncFsServerResponse.HOST_ENABLED:
                break
            else:
                raise ValueError(f"Unexpected response from server: {msg}")

        return SocketWrapper(self.sock)

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.sock is not None:
            self.sock.close()
            self.sock = None


class SocketWrapper:
    def __init__(self, sock):
        self.sock = sock

    def write(self, data):
        # This wrapper only handles report updates
        bytes_written = self.sock.send(FuncFsServerRequest.UPDATE_REPORT.serialize() + data)
        while True:
            msg = FuncFsServerResponse.from_bytes(self.sock.recv(1), byteorder='little')
            if msg is None:
                raise RuntimeError("Socket closed unexpectedly")
            elif msg == FuncFsServerResponse.USER_OVERRIDE:
                print("User override, waiting for server to unblock")
                while True:
                    msg = FuncFsServerResponse.from_bytes(self.sock.recv(1), byteorder='little')
                    if msg == FuncFsServerResponse.HOST_ENABLED:
                        print("Unblocked")
                        return bytes_written
                    else:
                        raise ValueError(f"Unexpected response from server: {msg}")
            elif msg != FuncFsServerResponse.ACK:
                raise ValueError(f"Unexpected response from server: {msg}")
            else:
                return bytes_written

    def flush(self):
        pass
