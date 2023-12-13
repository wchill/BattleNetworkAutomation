import os
import subprocess
import time
from typing import Tuple

import psutil
import win32api

from nx.controller.commands import ControllerRequest, ControllerResponse


class PipeWrapper:
    def __init__(self, process_id: int, pipe_handle: int):
        self.process_id = process_id
        self.pipe_handle = pipe_handle

    def write(self, command: ControllerRequest, data: bytes):
        import win32file

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


# https://stackoverflow.com/a/51239081/1502893
class WindowsNamedPipeSink:
    def __init__(self, process_name: str):
        self.process_name = process_name

    def connect_to_pipe(self) -> Tuple[PipeWrapper, bool]:
        import pywintypes
        import win32file
        import win32pipe

        existing_processes = {p.name(): p.pid for p in psutil.process_iter(attrs=["name", "pid"])}
        process_name = os.path.basename(self.process_name)
        process_exists = process_name in existing_processes.keys()
        if not process_exists:
            print(f"Starting process {self.process_name}")
            subprocess.Popen([self.process_name])
            while process_name not in existing_processes.keys():
                time.sleep(5)
                existing_processes = {p.name(): p.pid for p in psutil.process_iter(attrs=["name", "pid"])}
            process_id = existing_processes[process_name]
            print(f"Started pid {process_id}")
        else:
            process_id = existing_processes[process_name]
            print(f"Process already exists as pid {process_id}, not opening")

        while True:
            print(rf"Trying to open pipe \\.\pipe\XInputReportInjector\{process_id}")

            try:
                self.handle = win32file.CreateFile(
                    rf"\\.\pipe\XInputReportInjector\{process_id}",
                    win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                    0,
                    None,
                    win32file.OPEN_EXISTING,
                    0,
                    None,
                )
                res = win32pipe.SetNamedPipeHandleState(
                    self.handle, win32pipe.PIPE_READMODE_MESSAGE + win32pipe.PIPE_NOWAIT, None, None
                )
                if res == 0:
                    print(f"SetNamedPipeHandleState return code: {res}")

                time.sleep(1)

                success, resp = win32file.ReadFile(self.handle, 1024)

                msg = ControllerResponse.from_bytes(resp, byteorder="little")
                if msg == ControllerResponse.HOST_ENABLED:
                    print("Connected to controller host")
                    win32pipe.SetNamedPipeHandleState(self.handle, win32pipe.PIPE_READMODE_MESSAGE, None, None)
                    return PipeWrapper(process_id, self.handle), process_exists
                else:
                    raise ValueError(f"Unexpected response from server: {msg}")
            except pywintypes.error as e:
                if e.args[0] == 2:
                    # Pipe not open yet, retry after waiting
                    print("Pipe not open yet, retrying after 5 seconds")
                    time.sleep(5)
                elif e.args[0] == 109:
                    # Broken pipe
                    raise RuntimeError("Broken pipe") from e
                elif e.args[0] == 232:
                    # Nonblocking read returned no data
                    print("Pipe read returned no data, retrying after 1 second")
                    win32api.CloseHandle(self.handle)
                    time.sleep(1)
                else:
                    raise RuntimeError(win32api.GetLastError()) from e

            existing_processes = {p.name(): p.pid for p in psutil.process_iter(attrs=["name", "pid"])}
            process_id = existing_processes[process_name]

    def __enter__(self):
        return self.connect_to_pipe()

    def __exit__(self, exc_type, exc_val, exc_tb):
        import win32api

        if self.handle is not None:
            win32api.CloseHandle(self.handle)
            self.handle = None
