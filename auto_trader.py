from __future__ import annotations

import math
import multiprocessing
import time
from enum import Enum
from queue import Queue
from typing import Any, Callable, Dict, Generic, List, Tuple, TypeVar, Union

from discord.ext import commands

from bn_automation import image_processing
from bn_automation.controller import Button, Command, Controller, DPad
from bn_automation.script import Script
from chip import Chip, Sort
from chip_list import ChipList
from navicust_part import NaviCustPart
from navicust_part_list import NaviCustPartList

T = TypeVar("T")


class DiscordContext:
    def __init__(self, user_name: str, user_id: int, message_id: int, channel_id: int):
        self.user_name = user_name
        self.user_id = user_id
        self.message_id = message_id
        self.channel_id = channel_id

    @classmethod
    def create(cls, discord_context: commands.Context):
        return cls(
            discord_context.author.display_name,
            discord_context.author.id,
            discord_context.message.id,
            discord_context.channel.id,
        )


class TradeResult(Enum):
    Success = 0
    UnexpectedState = 1
    ControllerDisconnect = 2
    AlreadyInQueue = 3
    InvalidInput = 4
    UserTimeOut = 5
    Cancelled = 6
    CommunicationError = 7


class Node(Generic[T]):
    def __init__(self, obj: T):
        self.obj = obj
        self.neighbors: Dict[Union[Button, DPad], Node[T]] = {}

    def add(self, node: "Node[T]", button: Union[Button, DPad]) -> "Node[T]":
        self.neighbors[button] = node
        return self

    def __repr__(self) -> str:
        return repr(self.obj)

    def __hash__(self) -> int:
        return hash(self.obj)

    def search(self, target: T) -> List[Tuple[Union[Button, DPad], "Node[T]"]]:
        if self.obj == target:
            return []

        visited = set()
        q: Queue[Tuple[Node[T], List[Union[Button, DPad]], List[Node[T]]]] = Queue()
        q.put((self, [], []))
        visited.add(self)

        shortest = None

        while not q.empty():
            node, path, visited_nodes = q.get()
            if node.obj == target and (shortest is None or len(shortest) > len(path)):
                shortest = list(zip(path, visited_nodes))
            for controller_input, neighbor in node.neighbors.items():
                if neighbor not in visited:
                    visited.add(neighbor)
                    q.put((neighbor, path + [controller_input], visited_nodes + [neighbor]))

        if shortest is not None:
            return shortest

        raise RuntimeError(f"Path from {str(self.obj)} to {str(target)} not found")


def build_input_graph(obj_list: List[T]) -> List[Node[T]]:
    nodes = [Node(obj) for obj in obj_list]
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


class RoomCodeMessage:
    def __init__(self, discord_context: DiscordContext, obj: Any, image: bytes):
        self.discord_context = discord_context
        self.obj = str(obj)
        self.image = image


class AutoTrader(Script):
    def __init__(self, controller: Controller):
        super().__init__(controller)
        self.root_chip_node = self.build_all_chip_input_graphs()
        self.root_ncp_node = self.build_ncp_input_graph()

    @staticmethod
    def build_all_chip_input_graphs() -> Node[Chip]:
        graphs = [build_input_graph(ChipList.TRADABLE_CHIP_ORDER[sort]) for sort in Sort]
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

    @staticmethod
    def build_ncp_input_graph() -> Node[NaviCustPart]:
        ncp_graph = build_input_graph(NaviCustPartList.ALL_PARTS + [NaviCustPartList.NOTHING])
        return ncp_graph[0]

    def calculate_chip_inputs(self, chip: Chip) -> List[Tuple[Union[Button, DPad], Node[Chip]]]:
        return self.root_chip_node.search(chip)

    def calculate_ncp_inputs(self, ncp: NaviCustPart) -> List[Tuple[Union[Button, DPad], Node[NaviCustPart]]]:
        return self.root_ncp_node.search(ncp)

    def reset(self):
        self.home(wait_time=1000)
        self.plus(wait_time=1000)
        self.a()
        self.down()
        self.a(wait_time=500)

        # TODO: Wait for "Download Save Data"
        self.wait(5000)
        self.down()
        self.a()

        # TODO: Wait for "Close the software"
        self.wait(1000)
        self.a(wait_time=5000)
        self.up()
        self.a()

        # TODO: Wait for "Download complete.
        self.wait(5000)
        self.b(wait_time=1000)
        self.b()
        self.b()

        self.a()

        # TODO: Wait for "Select a user."
        self.wait(2000)
        self.a(wait_time=2000)
        self.a()

        # TODO: Wait for "PRESS ANY BUTTON"
        self.wait(60000)
        self.a()

        # TODO: Wait for "MAIN MENU"
        self.wait(15000)

        self.a(wait_time=1000)
        self.a(wait_time=10000)
        self.plus(wait_time=500)
        self.a(wait_time=3000)

        self.plus()
        self.up()
        self.up()
        self.a(wait_time=3000)

    def navigate_to_chip_trade_screen(self) -> bool:
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
        return self.wait_for_text(lambda ocr_text: ocr_text == "Sort : ID", (1054, 205), (162, 48), 10)

    def navigate_to_ncp_trade_screen(self) -> bool:
        # navigate to trade screen
        # Trade
        self.down()
        self.a()

        # Private Trade
        self.down()
        self.a()

        # Create Room
        self.a()

        # Program Trade
        self.down()
        self.a()

        # Next
        self.a()

        print("Waiting for ncp select")
        return self.wait_for_text(
            lambda ocr_text: ocr_text == "SuprArmr", (1080, 270), (200, 60), timeout=10, invert=False
        )

    """
    def check_lowest_chip_qty(self) -> int:
        self.navigate_to_trade_screen()
        self.repeat(self.plus, 5)
        self.repeat(self.up, 2)
        _, frame = self.capture.read()
        image_processing.run_tesseract_line(frame, top_left, size, invert)
    """

    def check_for_cancel(
        self, trade_cancelled: multiprocessing.Event, cancel_trade_for_user_id: multiprocessing.Value, user_id: int
    ) -> bool:
        cancel_lock = cancel_trade_for_user_id.get_lock()

        cancel_lock.acquire()
        if cancel_trade_for_user_id.value == user_id:
            cancel_trade_for_user_id.value = 0
            trade_cancelled.set()
            cancel_lock.release()
            return True
        trade_cancelled.set()
        cancel_lock.release()
        return False

    def get_last_inputs(self) -> List[str]:
        last_inputs = []
        for previous_input in self.last_inputs:
            if isinstance(previous_input, Command):
                buttons = previous_input.current_buttons
                dpad = previous_input.current_dpad
                left_angle, left_intensity = previous_input.current_left_stick
                right_angle, right_intensity = previous_input.current_right_stick

                input_strs = []
                if len(buttons) != 0:
                    input_strs.append(" | ".join([button.name for button in buttons]))
                if dpad != DPad.Center:
                    input_strs.append(dpad.name)
                if left_intensity != 0:
                    input_strs.append(f"LS {left_angle} {left_intensity}")
                if right_intensity != 0:
                    input_strs.append(f"RS {right_angle} {right_intensity}")
                if len(input_strs) == 0:
                    input_strs.append("nothing")
                input_str = ", ".join(input_strs)
                if previous_input.time > 0:
                    input_str += f" {math.ceil(previous_input.time / 8) * 8}ms"
                last_inputs.append(input_str)
            else:
                last_inputs.append(f"Wait {previous_input}ms")
        return last_inputs

    def trade(
        self,
        discord_context: DiscordContext,
        trade_item: T,
        navigate_func: Callable[[], bool],
        input_tuples: List[Tuple[Union[Button, DPad], Node[T]]],
        cancel_trade_for_user_id: multiprocessing.Value,
        trade_cancelled: multiprocessing.Event,
        image_send_queue: multiprocessing.JoinableQueue,
    ) -> Tuple[TradeResult, Union[bytes, str]]:
        print(f"Trading {str(trade_item)}")

        self.last_inputs.clear()

        success = navigate_func()
        if not success:
            return TradeResult.UnexpectedState, "Unable to open trade screen."

        for controller_input, selected_chip in input_tuples:
            if isinstance(controller_input, DPad):
                self.controller.press_dpad(controller_input)
            else:
                self.controller.press_button(controller_input)

        if self.check_for_cancel(trade_cancelled, cancel_trade_for_user_id, discord_context.user_id):
            self.repeat(self.b, 5, wait_time=200)
            self.up()
            return TradeResult.Cancelled, "Trade cancelled by user."

        self.a()
        self.a(wait_time=3000)

        print("Waiting for room code")
        if not self.wait_for_text(lambda ocr_text: ocr_text.startswith("Room Code: "), (1242, 89), (365, 54), 15):
            return TradeResult.UnexpectedState, "Unable to retrieve room code."

        frame = image_processing.capture()
        room_code_image = image_processing.crop_to_bounding_box(frame, (1242, 89), (400, 80), invert=True)
        image_bytestring = image_processing.convert_image_to_png_bytestring(room_code_image)

        # Send room code back to consumer, wait for it to be processed before continuing
        image_send_queue.put(RoomCodeMessage(discord_context, trade_item, image_bytestring))
        image_send_queue.join()

        start_time = time.time()
        print("Waiting 180s for user")
        while time.time() < start_time + 180:
            if self.check_for_cancel(trade_cancelled, cancel_trade_for_user_id, discord_context.user_id):
                self.b(wait_time=1000)
                self.a(wait_time=1000)
                print("Cancelling trade within timeout period")
                return TradeResult.Cancelled, "Trade cancelled by user."
            elif (
                image_processing.run_tesseract_line(image_processing.capture(), (660, 440), (620, 50))
                == "A communication error occurred."
            ):
                self.a(wait_time=1000)
                print("Communication error, restarting")
                return TradeResult.CommunicationError, "There was a communication error. Retrying."
            else:
                text = image_processing.run_tesseract_line(image_processing.capture(), (785, 123), (160, 60))
                if text == "1/15":
                    print("User joined lobby")
                    self.wait(500)
                    self.a(wait_time=1000)
                    self.a()
                    print("User completed trade")
                    if self.wait_for_text(lambda ocr_text: ocr_text == "Trade complete!", (815, 440), (310, 55), 20):
                        self.a(wait_time=1000)
                        if self.wait_for_text(lambda ocr_text: ocr_text == "NETWORK", (55, 65), (225, 50), 10):
                            print("Back at main menu")
                            self.wait(2000)
                            return TradeResult.Success, "Trade successful."
                        else:
                            return TradeResult.UnexpectedState, "I think the trade was successful, but something broke."
                    else:
                        return TradeResult.UnexpectedState, "Trade failed due to an unexpected state."

        self.b(wait_time=1000)
        self.a(wait_time=1000)
        return TradeResult.UserTimeOut, "Trade cancelled due to timeout."

    def trade_chip(
        self,
        discord_context: DiscordContext,
        chip: Chip,
        cancel_trade_for_user_id: multiprocessing.Value,
        trade_cancelled: multiprocessing.Event,
        image_send_queue: multiprocessing.JoinableQueue,
    ) -> Tuple[TradeResult, Union[bytes, str]]:
        return self.trade(
            discord_context,
            chip,
            self.navigate_to_chip_trade_screen,
            self.calculate_chip_inputs(chip),
            cancel_trade_for_user_id,
            trade_cancelled,
            image_send_queue,
        )

    def trade_ncp(
        self,
        discord_context: DiscordContext,
        ncp: NaviCustPart,
        cancel_trade_for_user_id: multiprocessing.Value,
        trade_cancelled: multiprocessing.Event,
        image_send_queue: multiprocessing.JoinableQueue,
    ) -> Tuple[TradeResult, Union[bytes, str]]:
        return self.trade(
            discord_context,
            ncp,
            self.navigate_to_ncp_trade_screen,
            self.calculate_ncp_inputs(ncp),
            cancel_trade_for_user_id,
            trade_cancelled,
            image_send_queue,
        )
