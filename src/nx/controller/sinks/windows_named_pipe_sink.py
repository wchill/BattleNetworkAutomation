import asyncio
import time

import win32api
import win32file

from nx.controller.commands import ControllerRequest, ControllerResponse


# https://stackoverflow.com/a/51239081/1502893
class WindowsNamedPipeSink:
    def connect_to_pipe(self):
        import pywintypes
        import win32file
        import win32pipe

        while True:
            try:
                self.handle = win32file.CreateFile(
                    r"\\.\pipe\XInputReportInjector",
                    win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                    0,
                    None,
                    win32file.OPEN_EXISTING,
                    0,
                    None,
                )
                res = win32pipe.SetNamedPipeHandleState(self.handle, win32pipe.PIPE_READMODE_MESSAGE, None, None)
                if res == 0:
                    print(f"SetNamedPipeHandleState return code: {res}")

                success, resp = win32file.ReadFile(self.handle, 1024)
                msg = ControllerResponse.from_bytes(resp, byteorder="little")
                if msg == ControllerResponse.HOST_ENABLED:
                    print("Connected to controller host")
                    return PipeWrapper(self.handle)
                else:
                    raise ValueError(f"Unexpected response from server: {msg}")
            except pywintypes.error as e:
                if e.args[0] == 2:
                    # Pipe not open yet, retry after waiting
                    time.sleep(1)
                elif e.args[0] == 109:
                    # Broken pipe
                    raise RuntimeError("Broken pipe") from e

    def __enter__(self):
        return self.connect_to_pipe()

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.handle is not None:
            win32api.CloseHandle(self.handle)
            self.handle = None


class PipeWrapper:
    def __init__(self, pipe_handle):
        self.pipe_handle = pipe_handle

    def write(self, command: ControllerRequest, data: bytes):
        success, bytes_written = win32file.WriteFile(self.pipe_handle, command.serialize() + data)
        while True:
            success, resp = win32file.ReadFile(self.pipe_handle, 1024)
            if resp is None or len(resp) == 0:
                raise RuntimeError("Pipe closed unexpectedly")
            msg = ControllerResponse.from_bytes(resp, byteorder="little")
            if msg == ControllerResponse.USER_OVERRIDE:
                print("User override, waiting for server to unblock")
                while True:
                    success, resp = win32file.ReadFile(self.pipe_handle, 1024)
                    msg = ControllerResponse.from_bytes(resp, byteorder="little")
                    if msg == ControllerResponse.HOST_ENABLED:
                        print("Unblocked, retrying")
                        success, bytes_written = win32file.WriteFile(self.pipe_handle, command.serialize() + data)
                        break
                    else:
                        raise ValueError(f"Unexpected response from server: {resp}")
            elif msg != ControllerResponse.ACK:
                raise ValueError(f"Unexpected response from server: {resp}")
            else:
                return bytes_written

    def flush(self):
        pass
