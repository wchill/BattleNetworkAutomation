import functools
import io
from enum import Enum, auto
from typing import Any, Dict, List

from PIL import Image, ImageDraw


class Color(Enum):
    White = "⚪"
    Pink = "<:pink:1105722810183196702>"
    Yellow = "🟡"
    Green = "🟢"
    Blue = "🔵"
    Red = "🔴"
    Nothing = auto()


COLORS = {
    Color.White: (245, 245, 245),
    Color.Yellow: (255, 235, 59),
    Color.Green: (100, 221, 23),
    Color.Blue: (21, 101, 192),
    Color.Red: (213, 0, 0),
    Color.Pink: (213, 0, 249),
}


class Bug(Enum):
    Nothing = auto()
    Activation = auto()
    Buster = auto()
    Custom = auto()
    Damage = auto()
    Emotion = auto()
    Encounter = auto()
    Movement = auto()
    Panel = auto()
    Result = auto()


@functools.total_ordering
class NaviCustPart:
    def __init__(
        self,
        name: str,
        color: Color,
        description: str,
        compression_code: str,
        bug: Bug,
        layout: List[str],
        internal_id: int,
    ):
        self.name = name
        self.color = color
        self.description = description
        self.compression_code = compression_code
        self.bug = bug
        self.layout = layout
        self.internal_id = internal_id

    @functools.cached_property
    def block_image(self) -> bytes:
        line_thickness = 2
        block_size = 20
        dimension = 5 * block_size + 6 * line_thickness

        im = Image.new(mode="RGB", size=(dimension, dimension), color=(0x4A, 0x6B, 0x8C))
        draw = ImageDraw.Draw(im)

        color = COLORS[self.color]
        darker = (int(color[0] * 0.6), int(color[1] * 0.6), int(color[2] * 0.6))

        for y, line in enumerate(self.layout):
            for x, sq in enumerate(line):
                left = line_thickness + (block_size + line_thickness) * x - 1
                right = left + block_size + 2
                top = line_thickness + (block_size + line_thickness) * y - 1
                bottom = top + block_size + 2
                if sq == " ":
                    continue
                elif sq == "X":
                    draw.rectangle((left, top, right, bottom), color, outline=(0, 0, 0), width=1)
                elif sq == "#":
                    midpoint_x = (left + right) / 2
                    midpoint_y = (top + bottom) / 2
                    draw.rectangle((left, top, right, bottom), color, outline=(0, 0, 0), width=1)
                    draw.line((midpoint_x, top, midpoint_x, bottom), fill=darker, width=2)
                    draw.line((left, midpoint_y, right, midpoint_y), fill=darker, width=2)
                    draw.rectangle((left, top, right, bottom), None, outline=(0, 0, 0), width=1)
                elif sq == "-":
                    draw.rectangle((left, top, right, bottom), darker, outline=(0, 0, 0), width=1)

        with io.BytesIO() as output:
            im.save(output, format="PNG")
            return output.getvalue()

    def __le__(self, other: "NaviCustPart") -> bool:
        return self.internal_id < other.internal_id

    def __eq__(self, other) -> bool:
        if other is None:
            return False
        return self.__dict__ == other.__dict__

    @classmethod
    def make(cls, ncp_dict: Dict[str, Any], internal_id: int) -> "NaviCustPart":
        name = ncp_dict["name"]
        color = Color[ncp_dict["color"]]
        description = ncp_dict["description"]
        compression_code = ncp_dict["compression"]
        bug = Bug[ncp_dict["bug"]]
        layout = ncp_dict["layout"]
        return cls(name, color, description, compression_code, bug, layout, internal_id)

    def __hash__(self) -> int:
        return hash((self.name, self.color, self.internal_id))

    def __repr__(self) -> str:
        if self.name == "Nothing":
            return "Nothing"
        return f"{self.name} ({self.color.name})"
