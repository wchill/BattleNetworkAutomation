import asyncio
import ipaddress
import socket

from ..commands import ControllerRequest, ControllerResponse
from . import ControllerSink


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

    async def connect(self):
        loop = asyncio.get_running_loop()

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        print(f"Connecting to {self.ip}:{self.port}")
        await loop.sock_connect(self.sock, (self.ip, self.port))
        print(f"Connected to {self.ip}:{self.port}")

        # wait for connection
        while True:
            msg = ControllerResponse.from_bytes(await loop.sock_recv(self.sock, 1), byteorder="little")
            if msg == ControllerResponse.HOST_ENABLED:
                print("Connected to controller host")
                break
            else:
                raise ValueError(f"Unexpected response from server: {msg}")

        return SocketWrapper(self.sock)

    def __enter__(self):
        return asyncio.run(self.connect())

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.sock is not None:
            self.sock.close()
            self.sock = None


class SocketWrapper:
    def __init__(self, sock):
        self.sock = sock

    def write(self, command: ControllerRequest, data: bytes):
        bytes_written = self.sock.send(command.serialize() + data)
        while True:
            msg = ControllerResponse.from_bytes(self.sock.recv(1), byteorder="little")
            if msg is None:
                raise RuntimeError("Socket closed unexpectedly")
            elif msg == ControllerResponse.USER_OVERRIDE:
                print("User override, waiting for server to unblock")
                while True:
                    msg = ControllerResponse.from_bytes(self.sock.recv(1), byteorder="little")
                    if msg == ControllerResponse.HOST_ENABLED:
                        print("Unblocked, retrying")
                        self.sock.send(command.serialize() + data)
                        break
                    else:
                        raise ValueError(f"Unexpected response from server: {msg}")
            elif msg != ControllerResponse.ACK:
                raise ValueError(f"Unexpected response from server: {msg}")
            else:
                return bytes_written

    def flush(self):
        pass
