import functools
import json
import os
from pathlib import Path
from typing import List, Optional

from chip import Chip, Code, Element, Sort

_nothing = Chip("Nothing", "999", Code.Star, 0, Element.Null, 100, Chip.NOTHING)
SORT_METHODS = [Sort.ID, Sort.ABCDE, Sort.Code, Sort.Attack, Sort.Element, Sort.No, Sort.MB]


def _read_chips_from_file(filename: str, chip_type: int) -> List[Chip]:
    data_dir = Path(os.path.join(os.path.dirname(__file__), "src/bn_automation/data"))

    with (data_dir / filename).open() as f:
        standard_chips = json.load(f)
        retval = []
        for chip in standard_chips:
            retval += Chip.make(chip, chip_type)
    return retval


@functools.cache
def _get_standard_chips() -> List[Chip]:
    return _read_chips_from_file("chips.json", Chip.STANDARD)


@functools.cache
def _get_mega_chips() -> List[Chip]:
    return _read_chips_from_file("megachips.json", Chip.MEGA)


@functools.cache
def _get_giga_chips() -> List[Chip]:
    return _read_chips_from_file("gigachips.json", Chip.GIGA)


@functools.cache
def _get_all_chips() -> List[Chip]:
    return _get_standard_chips() + _get_mega_chips() + _get_giga_chips()


@functools.cache
def _get_untradable_chips() -> List[Chip]:
    return _read_chips_from_file("untradable.json", Chip.STANDARD)


@functools.cache
def _get_tradable_standard_chips() -> List[Chip]:
    return sorted(set(_get_standard_chips()) - set(_get_untradable_chips()))


@functools.cache
def _get_tradable_chips() -> List[Chip]:
    return _get_tradable_standard_chips() + _get_mega_chips()


@functools.cache
def calculate_sort_result(sort: Sort) -> List[Chip]:
    all_tradable_chips = _get_tradable_chips()

    if sort == Sort.ID:
        return sorted(all_tradable_chips, key=lambda chip: (chip.chip_type, chip.sorting_chip_id, chip.code)) + [
            _nothing
        ]
    elif sort == Sort.ABCDE:
        return sorted(all_tradable_chips, key=lambda chip: (chip.name.lower(), chip.chip_type, chip.code)) + [_nothing]
    elif sort == Sort.Code:
        return sorted(all_tradable_chips, key=lambda chip: (chip.code, chip.chip_type, chip.sorting_chip_id)) + [
            _nothing
        ]
    elif sort == Sort.Attack:
        return sorted(
            all_tradable_chips, key=lambda chip: (-chip.atk, chip.chip_type, chip.sorting_chip_id, chip.code)
        ) + [_nothing]
    elif sort == Sort.Element:
        return sorted(
            all_tradable_chips, key=lambda chip: (chip.element, chip.chip_type, chip.sorting_chip_id, chip.code)
        ) + [_nothing]
    elif sort == Sort.MB:
        return sorted(
            all_tradable_chips, key=lambda chip: (chip.mb, chip.chip_type, chip.sorting_chip_id, chip.code)
        ) + [_nothing]
    elif sort == Sort.No:
        # Sentinel values to make things easier
        return [Chip("", "", Code.Star, 0, Element.Null, 0, Chip.NOTHING)] * 9
    else:
        raise RuntimeError("Unsupported sort type")


class ChipList:
    @classmethod
    def get_chip(cls, name: str, code: str) -> Optional[Chip]:
        try:
            if code == "*":
                chip_code = Code.Star
            else:
                chip_code = Code[code.upper()]

            return cls.CHIP_INDEX.get((name.lower(), chip_code))
        except KeyError:
            return None

    STANDARD_CHIPS = _get_standard_chips()
    MEGA_CHIPS = _get_mega_chips()
    GIGA_CHIPS = _get_giga_chips()
    ALL_CHIPS = _get_all_chips()
    UNTRADABLE_STANDARD_CHIPS = _get_untradable_chips()
    TRADABLE_STANDARD_CHIPS = _get_tradable_standard_chips()
    NOTHING = _nothing

    TRADABLE_CHIP_ORDER = {method: calculate_sort_result(method) for method in SORT_METHODS}
    CHIP_INDEX = {(chip.name.lower(), chip.code): chip for chip in _get_tradable_chips()}
