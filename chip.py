import functools
import os
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List


class Sort(Enum):
    ID = 0
    ABCDE = 1
    Code = 2
    Attack = 3
    Element = 4
    No = 5
    MB = 6


@functools.total_ordering
class Element(Enum):
    Fire = 1
    Water = 2
    Elec = 3
    Wood = 4
    Sword = 5
    Wind = 6
    Cursor = 7
    Object = 8
    Plus = 9
    Break = 10
    Null = 11

    def __le__(self, other):
        return self.value < other.value

    def __eq__(self, other):
        return self.value == other.value


@functools.total_ordering
class Code(Enum):
    A = 1
    B = 2
    C = 3
    D = 4
    E = 5
    F = 6
    G = 7
    H = 8
    I = 9
    J = 10
    K = 11
    L = 12
    M = 13
    N = 14
    O = 15
    P = 16
    Q = 17
    R = 18
    S = 19
    T = 20
    U = 21
    V = 22
    W = 23
    X = 24
    Y = 25
    Z = 26
    Star = 27

    def __le__(self, other):
        return self.value < other.value

    def __eq__(self, other):
        return self.value == other.value

    def __hash__(self):
        return self.value

    def __str__(self):
        if self == Code.Star:
            return "*"
        return self.name


@functools.total_ordering
class Chip:
    STANDARD = 1
    MEGA = 2
    GIGA = 3
    NOTHING = 4

    def __init__(
        self, name: str, chip_id: str, code: Code, atk: int, element: Element, mb: int, chip_type: int, description: str
    ):
        self.name = name
        self.chip_id = chip_id
        self.code = code
        self.atk = atk
        self.element = element
        self.mb = mb
        self.chip_type = chip_type
        self.description = description

    @property
    def sorting_chip_id(self) -> str:
        # Ugly hack to get proper sorting
        return "007 " + self.chip_id if self.is_link_navi_chip() else self.chip_id

    @property
    def chip_image_path(self) -> str:
        # TODO: ew

        base_path = Path(os.path.join(os.path.dirname(__file__), "src/bn_automation/chip_images"))
        if self.chip_type == Chip.STANDARD:
            filename = f"BN6Chip{self.chip_id}.png"
        elif self.chip_type == Chip.MEGA:
            if self.is_link_navi_chip():
                filename = f"BN6{self.chip_id[1]}MChip{self.get_chip_id()}.png"
            else:
                filename = f"BN6MChip{self.get_chip_id()}.png"
        elif self.chip_type == Chip.GIGA:
            filename = f"BN6{self.chip_id[1]}GChip{self.get_chip_id()}.png"
        else:
            raise RuntimeError(f"Bad chip type {self.chip_type}")

        return str(base_path / filename)

    def is_link_navi_chip(self) -> bool:
        return self.chip_id.startswith("C")

    def get_chip_id(self) -> str:
        return self.chip_id.split(" ")[-1]

    def __le__(self, other: "Chip") -> bool:
        if self.chip_type != other.chip_type:
            return self.chip_type < other.chip_type

        if self.sorting_chip_id == other.sorting_chip_id:
            if self.code == Code.Star and other.code != Code.Star:
                return False
            elif self.code != Code.Star and other.code == Code.Star:
                return True
            else:
                return self.code < other.code

        return self.sorting_chip_id < other.sorting_chip_id

    def __eq__(self, other) -> bool:
        if other is None:
            return False
        return self.__dict__ == other.__dict__

    @classmethod
    def make(cls, chip_dict: Dict[str, Any], chip_type: int) -> List["Chip"]:
        ret = []
        for code in chip_dict["codes"]:
            if code == "*":
                code = "Star"
            ret.append(
                cls(
                    chip_dict["name"],
                    chip_dict["id"],
                    Code[code],
                    chip_dict["atk"],
                    Element[chip_dict["element"]],
                    chip_dict["mb"],
                    chip_type,
                    chip_dict["description"],
                )
            )
        return ret

    def __hash__(self) -> int:
        return hash((self.name, self.chip_id, self.code, self.element.value, self.atk, self.mb, self.chip_type))

    def __repr__(self) -> str:
        if self.chip_type == 3:
            return "Nothing"
        return f"{self.chip_id} - {self.name} {self.code} ({self.element.name}, {self.atk}, {self.mb}MB)"

    def __str__(self) -> str:
        if self.chip_type == 3:
            return "Nothing"
        return f"{self.name} {self.code}"
