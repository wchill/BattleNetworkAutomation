import io


class Crc8WrappedFileLikeObject(io.IOBase):
    def __init__(self, file):
        super().__init__()
        self.file = file

    # Compute CRC8
    # https://www.microchip.com/webdoc/AVRLibcReferenceManual/group__util__crc_1gab27eaaef6d7fd096bd7d57bf3f9ba083.html
    @staticmethod
    def crc8_ccitt(old_crc: int, new_data: int) -> int:
        data = old_crc ^ new_data

        for i in range(8):
            if (data & 0x80) != 0:
                data = data << 1
                data = data ^ 0x07
            else:
                data = data << 1
            data = data & 0xff
        return data

    def write(self, data: bytes) -> int:
        crc8 = 0
        for b in data:
            crc8 = self.crc8_ccitt(crc8, b)
        return self.port.write(data + bytearray([crc8]))

    def __getattr__(self, item):
        return getattr(self.file, item)
