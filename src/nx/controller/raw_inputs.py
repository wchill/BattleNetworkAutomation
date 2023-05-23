from enum import IntFlag


class ExtendedIntFlagEnum(IntFlag):
    @classmethod
    def All(cls):
        return [c.value for c in cls]

    @classmethod
    def from_str(cls, label):
        mapping = {e.name.lower(): e for e in cls}
        return mapping[label.lower()]


class RawButton(ExtendedIntFlagEnum):
    Nothing = 0x0000
    Y = 0x0001
    B = 0x0002
    A = 0x0004
    X = 0x0008
    L = 0x0010
    R = 0x0020
    ZL = 0x0040
    ZR = 0x0080
    Minus = 0x0100
    Plus = 0x0200
    L3 = 0x0400
    R3 = 0x0800
    Home = 0x1000
    Capture = 0x2000


class _RawDPad:
    SHIFT_BITS = 16

    Center = 0x08 << SHIFT_BITS
    Up = 0x00 << SHIFT_BITS
    UpRight = 0x01 << SHIFT_BITS
    Right = 0x02 << SHIFT_BITS
    DownRight = 0x03 << SHIFT_BITS
    Down = 0x04 << SHIFT_BITS
    DownLeft = 0x05 << SHIFT_BITS
    Left = 0x06 << SHIFT_BITS
    UpLeft = 0x07 << SHIFT_BITS

    Cardinals = [Up, Right, Down, Left]
    Diagonals = [UpRight, DownRight, UpLeft, DownLeft]
    """
    NONE = 0x00 << SHIFT_BITS
    UP = 0x01 << SHIFT_BITS
    RIGHT = 0x02 << SHIFT_BITS
    DOWN = 0x04 << SHIFT_BITS
    LEFT = 0x08 << SHIFT_BITS
    UP_RIGHT = UP + RIGHT
    DOWN_RIGHT = DOWN + RIGHT
    UP_LEFT = UP + LEFT
    DOWN_LEFT = DOWN + LEFT

    Cardinals = [UP, RIGHT, DOWN, LEFT]
    Diagonals = [UP_RIGHT, DOWN_RIGHT, UP_LEFT, DOWN_LEFT]
    """


class RawDPad(ExtendedIntFlagEnum):
    Center = _RawDPad.Center
    Up = _RawDPad.Up
    UpRight = _RawDPad.UpRight
    Right = _RawDPad.Right
    DownRight = _RawDPad.DownRight
    Down = _RawDPad.Down
    DownLeft = _RawDPad.DownLeft
    Left = _RawDPad.Left
    UpLeft = _RawDPad.UpLeft


def to_hex(shift_bits, x: int, y: int):
    return ((y << 8) + x) << shift_bits


class RawLeftStick:
    SHIFT_BITS = 40

    Center = to_hex(SHIFT_BITS, 0x80, 0x80)
    Right = to_hex(SHIFT_BITS, 0xFF, 0x80)
    UpRight = to_hex(SHIFT_BITS, 0xFF, 0x00)
    Up = to_hex(SHIFT_BITS, 0x80, 0x00)
    UpLeft = to_hex(SHIFT_BITS, 0x00, 0x00)
    Left = to_hex(SHIFT_BITS, 0x00, 0x80)
    DownLeft = to_hex(SHIFT_BITS, 0x00, 0xFF)
    Down = to_hex(SHIFT_BITS, 0x80, 0xFF)
    DownRight = to_hex(SHIFT_BITS, 0xFF, 0x00)

    @classmethod
    def All(cls):
        return [cls.Center, cls.Right, cls.UpRight, cls.Up, cls.UpLeft, cls.Left, cls.DownLeft, cls.Down, cls.DownRight]


class RawRightStick:
    SHIFT_BITS = 24

    Center = to_hex(SHIFT_BITS, 0x80, 0x80)
    Right = to_hex(SHIFT_BITS, 0xFF, 0x80)
    UpRight = to_hex(SHIFT_BITS, 0xFF, 0x00)
    Up = to_hex(SHIFT_BITS, 0x80, 0x00)
    UpLeft = to_hex(SHIFT_BITS, 0x00, 0x00)
    Left = to_hex(SHIFT_BITS, 0x00, 0x80)
    DownLeft = to_hex(SHIFT_BITS, 0x00, 0xFF)
    Down = to_hex(SHIFT_BITS, 0x80, 0xFF)
    DownRight = to_hex(SHIFT_BITS, 0xFF, 0x00)

    @classmethod
    def All(cls):
        return [cls.Center, cls.Right, cls.UpRight, cls.Up, cls.UpLeft, cls.Left, cls.DownLeft, cls.Down, cls.DownRight]


EMPTY_REPORT = (RawButton.Nothing + RawDPad.Center + RawLeftStick.Center + RawRightStick.Center).to_bytes(
    8, byteorder="little"
)
