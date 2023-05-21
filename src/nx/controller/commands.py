from enum import IntEnum


class ControllerRequest(IntEnum):
    UPDATE_REPORT = 0x00
    UPDATE_REPORT_N_TIMES = 0x01
    STOP = 0xFF

    def serialize(self):
        return self.value.to_bytes(1, byteorder="little", signed=False)


class ControllerResponse(IntEnum):
    HOST_ENABLED = 0x00
    ACK = 0x01
    NACK = 0x02
    USER_OVERRIDE = 0x03
    UNKNOWN_ERROR = 0xFF

    def serialize(self):
        return self.value.to_bytes(1, byteorder="little", signed=False)
