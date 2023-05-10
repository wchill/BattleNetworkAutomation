import collections
import functools
import json
import os
from typing import Dict, List, Optional, Tuple, Union

from navicust_part import Bug, Color, NaviCustPart

_nothing = NaviCustPart("Nothing", Color.Nothing, "Nothing", "", Bug.Nothing, ["     "] * 5, 999)


@functools.cache
def _get_navicust_parts() -> List[NaviCustPart]:
    with open(os.path.join(os.path.dirname(__file__), "src/bn_automation/data/navicust.json")) as f:
        ncp_data = json.load(f)
        return [NaviCustPart.make(data, idx) for idx, data in enumerate(ncp_data)]


def _create_ncp_index() -> Dict[Tuple[str, Color], NaviCustPart]:
    parts = _get_navicust_parts()
    index = {(ncp.name.lower(), ncp.color): ncp for ncp in parts}
    count = collections.defaultdict(int)
    for part in parts:
        count[part] += 1

    for part, part_count in count.items():
        if part_count == 1:
            index[(part.name, None)] = part

    return index


class NaviCustPartList:
    @classmethod
    def get_ncp(cls, name: str, color: Union[Color, str]) -> Optional[NaviCustPart]:
        try:
            if isinstance(color, Color):
                ncp_color = color
            else:
                ncp_color = Color[color.lower().capitalize()]

            return cls.PARTS_INDEX.get((name.lower(), ncp_color))
        except KeyError:
            return None

    @classmethod
    def get_parts_by_color(cls, color: Union[Color, str]) -> List[NaviCustPart]:
        if isinstance(color, Color):
            ncp_color = color
        else:
            ncp_color = Color[color.lower().capitalize()]

        retval = []
        for ncp in cls.ALL_PARTS:
            if ncp.color == ncp_color:
                retval.append(ncp)
        return retval

    @classmethod
    def get_parts_by_name(cls, name: str) -> List[NaviCustPart]:
        retval = []
        for ncp in cls.ALL_PARTS:
            if ncp.name.lower() == name.lower():
                retval.append(ncp)
        return retval

    ALL_PARTS = _get_navicust_parts()
    NOTHING = _nothing

    PARTS_INDEX = {(ncp.name.lower(), ncp.color): ncp for ncp in _get_navicust_parts()}
