import functools
import json
import os
import queue
import time
from enum import Enum
from pathlib import Path
from queue import Queue
from typing import Callable, Dict, List, Tuple, Union

import cv2 as cv

from bn_automation import image_processing
from bn_automation.controller import Button, Controller, DPad
from bn_automation.script import Script


class FailureReason(Enum):
    UnexpectedState = 1
    ControllerDisconnect = 2
    AlreadyInQueue = 3
    InvalidInput = 4
    UserTimeOut = 5


FailureCallback = Callable[[FailureReason, str], None]


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
    NOTHING = 3

    def __init__(self, name: str, chip_id: str, code: Code, atk: int, element: Element, mb: int, chip_type: int):
        self.name = name
        self.chip_id = chip_id
        self.code = code
        self.atk = atk
        self.element = element
        self.mb = mb
        self.chip_type = chip_type

    @property
    def sorting_chip_id(self) -> str:
        # Ugly hack to get proper sorting
        return "007 " + self.chip_id if self.is_link_navi_chip() else self.chip_id

    def is_link_navi_chip(self) -> bool:
        return self.chip_id.startswith("C")

    def get_chip_id(self) -> str:
        return self.chip_id.split(" ")[-1]

    def __le__(self, other: "Chip"):
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

    def __eq__(self, other):
        if other is None:
            return False
        return self.__dict__ == other.__dict__

    @classmethod
    def make(cls, d, t):
        ret = []
        for code in d["codes"]:
            if code == "*":
                code = "Star"
            ret.append(cls(d["name"], d["id"], Code[code], d["atk"], Element[d["element"]], d["mb"], t))
        return ret

    def __hash__(self):
        return hash((self.name, self.chip_id, self.code, self.element.value, self.atk, self.mb, self.chip_type))

    def __repr__(self) -> str:
        if self.chip_type == 3:
            return "Nothing"
        return f"{self.chip_id} - {self.name} {self.code} ({self.element.name}, {self.atk}, {self.mb}MB)"


class Node:
    def __init__(self, chip: Chip):
        self.chip = chip
        self.neighbors: Dict[Union[Button, DPad], Node] = {}

    def add(self, node: "Node", button: Union[Button, DPad]) -> "Node":
        self.neighbors[button] = node
        return self

    def __repr__(self):
        return repr(self.chip)

    def __hash__(self):
        return hash(self.chip)

    def search(self, target: Chip) -> List[Tuple[Union[Button, DPad], "Node"]]:
        if self.chip == target:
            return []

        visited = set()
        q: Queue[Tuple[Node, List[Union[Button, DPad]], List[Node]]] = Queue()
        q.put((self, [], []))
        visited.add(self)

        shortest = None

        while not q.empty():
            node, path, visited_nodes = q.get()
            if node.chip == target and (shortest is None or len(shortest) > len(path)):
                shortest = list(zip(path, visited_nodes))
            for controller_input, neighbor in node.neighbors.items():
                if neighbor not in visited:
                    visited.add(neighbor)
                    q.put((neighbor, path + [controller_input], visited_nodes + [neighbor]))

        if shortest is not None:
            return shortest

        raise RuntimeError(f"Path from {self.chip.name} {self.chip.code} to {target.name} {target.code} not found")


def build_input_graph(chip_list: List[Chip]) -> List[Node]:
    nodes = [Node(chip) for chip in chip_list]
    for i in range(1, len(nodes) - 1):
        node = nodes[i]
        node.add(nodes[min((i + 8), len(nodes) - 1)], Button.R)
        node.add(nodes[max((i - 8), 0)], Button.L)
        node.add(nodes[(i + 1) % len(nodes)], DPad.Down)
        node.add(nodes[(i - 1) % len(nodes)], DPad.Up)

    start = nodes[0]
    end = nodes[-1]

    start.add(nodes[1], DPad.Down)
    start.add(end, DPad.Up)
    start.add(nodes[8], Button.R)
    start.add(end, Button.L)

    end.add(start, DPad.Down)
    end.add(nodes[-2], DPad.Up)
    end.add(start, Button.R)
    end.add(nodes[-9], Button.L)
    return nodes


class AutoTrader(Script):
    def __init__(self, controller: Controller, capture: cv.VideoCapture):
        super().__init__(controller, capture)

        data_dir = Path(os.path.join(os.path.dirname(__file__), "src/bn_automation/data"))

        with (data_dir / "chips.json").open() as f:
            standard_chips = json.load(f)
            self.standard_chips = []
            for chip in standard_chips:
                self.standard_chips += Chip.make(chip, Chip.STANDARD)

        with (data_dir / "megachips.json").open() as f:
            mega_chips = json.load(f)
            self.mega_chips = []
            for chip in mega_chips:
                self.mega_chips += Chip.make(chip, Chip.MEGA)

        with (data_dir / "untradable.json").open() as f:
            untradable_standard_chips = json.load(f)
            self.untradable_standard_chips = []
            for chip in untradable_standard_chips:
                self.untradable_standard_chips += Chip.make(chip, Chip.STANDARD)

        self.tradable_standard_chips = sorted(set(self.standard_chips) - set(self.untradable_standard_chips))

        sort_methods = [Sort.ID, Sort.ABCDE, Sort.Code, Sort.Attack, Sort.Element, Sort.No, Sort.MB]
        self.nothing_chip = Chip("Nothing", "999", Code.Star, 0, Element.Null, 100, Chip.NOTHING)

        self.tradable_chip_order = {
            method: self.calculate_sort_result(method) for method in sort_methods if method != Sort.No
        }

        self.chip_index = {
            (chip.name.lower(), chip.code): chip for chip in self.tradable_standard_chips + self.mega_chips
        }
        self.root_node = self.build_all_input_graphs()

        self.trading_queue = Queue()
        self.waiting_users = {}

    def get_chip(self, name: str, code: Code) -> Chip:
        return self.chip_index.get((name.lower(), code))

    def calculate_sort_result(self, sort: Sort) -> List[Chip]:
        all_tradable_chips = self.tradable_standard_chips + self.mega_chips

        if sort == Sort.ID:
            return sorted(all_tradable_chips, key=lambda chip: (chip.chip_type, chip.sorting_chip_id, chip.code)) + [
                self.nothing_chip
            ]
        elif sort == Sort.ABCDE:
            return sorted(all_tradable_chips, key=lambda chip: (chip.name.lower(), chip.chip_type, chip.code)) + [
                self.nothing_chip
            ]
        elif sort == Sort.Code:
            return sorted(all_tradable_chips, key=lambda chip: (chip.code, chip.chip_type, chip.sorting_chip_id)) + [
                self.nothing_chip
            ]
        elif sort == Sort.Attack:
            return sorted(
                all_tradable_chips, key=lambda chip: (-chip.atk, chip.chip_type, chip.sorting_chip_id, chip.code)
            ) + [self.nothing_chip]
        elif sort == Sort.Element:
            return sorted(
                all_tradable_chips, key=lambda chip: (chip.element, chip.chip_type, chip.sorting_chip_id, chip.code)
            ) + [self.nothing_chip]
        elif sort == Sort.MB:
            return sorted(
                all_tradable_chips, key=lambda chip: (chip.mb, chip.chip_type, chip.sorting_chip_id, chip.code)
            ) + [self.nothing_chip]
        elif sort == Sort.No:
            # Sentinel values to make things easier
            return [Chip("", "", Code.Star, 0, Element.Null, 0, Chip.NOTHING)] * 9
        else:
            raise RuntimeError("Unsupported sort type")

    def build_all_input_graphs(self) -> Node:
        graphs = [build_input_graph(self.calculate_sort_result(sort)) for sort in Sort]
        id_root = graphs[0][0]
        abcde_root = graphs[1][0]
        code_root = graphs[2][0]
        atk_root = graphs[3][0]
        element_root = graphs[4][0]
        no_root = graphs[5][0]
        mb_root = graphs[6][0]

        id_root.add(abcde_root, Button.Plus)
        abcde_root.add(code_root, Button.Plus)
        code_root.add(atk_root, Button.Plus)
        atk_root.add(element_root, Button.Plus)
        element_root.add(no_root, Button.Plus)
        no_root.add(mb_root, Button.Plus)
        mb_root.add(id_root, Button.Plus)
        return id_root

    def calculate_inputs(self, chip: Chip) -> List[Tuple[Union[Button, DPad], Node]]:
        return self.root_node.search(chip)

    def add_to_queue(
        self,
        user: str,
        chip: Chip,
        ready_cb: Callable[[str, Chip, bytes], None],
        failure_cb: FailureCallback,
        added_cb: Callable[[str], None],
    ) -> int:
        if user in self.waiting_users:
            failure_cb(FailureReason.AlreadyInQueue, "Cannot request when you are already in the queue.")
        elif chip is None:
            failure_cb(FailureReason.InvalidInput, "Invalid chip specified.")
        else:
            self.waiting_users[user] = chip
            self.trading_queue.put((user, chip, ready_cb, failure_cb))
            added_cb(
                f"Added your request for {chip.name} to the queue. There are {self.trading_queue.qsize() - 1} request(s) ahead of you. Make sure DMs are enabled."
            )
        return self.trading_queue.qsize()

    def remove_from_queue(self, user: str):
        try:
            self.waiting_users.pop(user)
        except KeyError:
            pass

    def process_queue(self) -> None:
        for i in range(90):
            print(f"{90 - i} chips needed before reset.")

            while True:
                try:
                    user, chip, ready_cb, failure_cb = self.trading_queue.get(block=True, timeout=10.0)
                    if user in self.waiting_users and self.waiting_users[user] == chip:
                        break
                except queue.Empty:
                    self.x()

            try:
                input_tuples = self.calculate_inputs(chip)
                print(f"Trading {chip} to {user}")

                print("Navigating to trade screen")
                self.wait(3.0)
                # navigate to trade screen
                # Trade
                self.down()
                self.a()

                # Private Trade
                self.down()
                self.a()

                # Create Room
                self.a()

                # Chip Trade
                self.a()

                # Next
                self.a()

                print("Waiting for chip select")
                if not self.wait_for_text(lambda ocr_text: ocr_text == "Sort : ID", (1054, 205), (162, 48), 30):
                    failure_cb(FailureReason.UnexpectedState, "Timed out waiting for chip select.")
                    print("Timeout waiting for chip select")
                    self.waiting_users.pop(user)
                    return

                self.wait(1.0)

                for controller_input, selected_chip in input_tuples:
                    print(controller_input, selected_chip)
                    if isinstance(controller_input, DPad):
                        self.controller.press_dpad(controller_input)
                    else:
                        self.controller.press_button(controller_input)

                self.a()
                self.a(wait_time=3.0)

                print("Waiting for room code")
                if not self.wait_for_text(
                    lambda ocr_text: ocr_text.startswith("Room Code: "), (1242, 89), (365, 54), 30
                ):
                    failure_cb(FailureReason.UnexpectedState, "Timed out waiting for room code.")
                    print("Timeout waiting for room code")
                    self.waiting_users.pop(user)
                    return

                room_code_image = image_processing.crop_image(self.capture.read()[1], (1242, 89), (365, 60))
                image_bytestring = image_processing.convert_image_to_png_bytestring(room_code_image)

                ready_cb(user, chip, image_bytestring)

                print("Waiting for user")
                # Give the coroutine time to execute
                self.wait(3.0)

                # Select user, etc
                trade_finished = False
                start_time = time.time()
                while time.time() < start_time + 180:
                    if user not in self.waiting_users:
                        # User cancelled
                        self.b()
                        self.wait(1.0)
                        self.a()
                        self.wait(1.0)
                        trade_finished = True
                        break
                    elif self.wait_for_text(lambda ocr_text: ocr_text == "Trade complete!", (815, 440), (309, 55), 3):
                        self.remove_from_queue(user)
                        self.a(wait_time=5.0)
                        trade_finished = True
                        break
                    self.a()
                    print(f"Seconds elapsed: {time.time() - start_time}")

                if not trade_finished:
                    failure_cb(FailureReason.UserTimeOut, "Timed out waiting for trade complete, trade cancelled.")
                    print("Timeout waiting for trade complete")

                    self.remove_from_queue(user)
                    self.waiting_users.pop(user)

                    # Exit to menu
                    self.b()
                    self.wait(1.0)
                    self.a()
                    self.wait(1.0)
                    continue
            except Exception as e:
                import traceback

                traceback.print_exc()
                failure_cb(FailureReason.UnexpectedState, f"{e.__class__.__name__}: {e}")
