from __future__ import annotations

import collections
import json
import logging
import multiprocessing
import os
import pickle
import queue
import time
from typing import Any, Dict, List, Optional, Tuple, Union

import discord

from auto_trader import AutoTrader, DiscordContext, RoomCodeMessage, TradeResult
from bn_automation import image_processing
from bn_automation.controller import Button, Controller
from bn_automation.controller.sinks import SocketSink
from chip import Chip
from navicust_part import NaviCustPart
from utils import MessageReaction

logger = logging.getLogger(__name__)


class TradeCommand:
    REQUEST_CHIP = 1
    CANCEL_REQUEST = 2
    LIST_QUEUE = 3
    CLEAR_QUEUE = 4
    PAUSE_QUEUE = 5
    SCREEN_CAPTURE = 6

    def __init__(self, command: int, discord_context: DiscordContext, **kwargs: Any):
        self.command = command
        self.discord_context = discord_context
        self.data = kwargs

    @property
    def user_id(self) -> int:
        return self.discord_context.user_id

    @property
    def user_name(self) -> str:
        return self.discord_context.user_name


class RequestCommand(TradeCommand):
    def __init__(self, discord_context: DiscordContext, trade_item: Union[Chip, NaviCustPart]):
        super().__init__(command=TradeCommand.REQUEST_CHIP, discord_context=discord_context, trade_item=trade_item)

    @property
    def trade_item(self) -> Union[Chip, NaviCustPart]:
        return self.data["trade_item"]


class CancelCommand(TradeCommand):
    def __init__(self, discord_context: DiscordContext):
        super().__init__(command=TradeCommand.CANCEL_REQUEST, discord_context=discord_context)


class ListQueueCommand(TradeCommand):
    def __init__(self, discord_context: DiscordContext):
        super().__init__(command=TradeCommand.LIST_QUEUE, discord_context=discord_context)


class ClearQueueCommand(TradeCommand):
    def __init__(self, discord_context: DiscordContext):
        super().__init__(command=TradeCommand.CLEAR_QUEUE, discord_context=discord_context)


class PauseQueueCommand(TradeCommand):
    def __init__(self, discord_context: DiscordContext):
        super().__init__(command=TradeCommand.PAUSE_QUEUE, discord_context=discord_context)


class ScreenCaptureCommand(TradeCommand):
    def __init__(self, discord_context: DiscordContext):
        super().__init__(command=TradeCommand.SCREEN_CAPTURE, discord_context=discord_context)


class DiscordMessageReplyRequest:
    def __init__(
        self,
        discord_context: DiscordContext,
        message: Optional[Union[str, Dict[str, Any]]],
        reaction: Optional[MessageReaction],
    ):
        self.discord_context = discord_context
        self.message = message
        self.reaction = reaction


class UserTradeStats:
    def __init__(self, user_id: int):
        self.user_id = user_id
        self.trades: Dict[Union[Chip, NaviCustPart], int] = collections.defaultdict(int)

    def __setstate__(self, state):
        if "chips" in state:
            chips = state.pop("chips")
            state["trades"] = chips
        self.__dict__ = state

    def __getstate__(self):
        state = self.__dict__
        if "chips" in state:
            chips = state.pop("chips")
            state["trades"] = chips
        return state

    def add_trade(self, chip: Chip):
        self.trades[chip] += 1

    def get_total_trade_count(self) -> int:
        total = 0
        for qty in self.trades.values():
            total += qty
        return total

    def get_trades_by_trade_count(self) -> List[Tuple[Chip, int]]:
        return [(k, v) for k, v in sorted(self.trades.items(), key=lambda item: item[1], reverse=True)]


class BotTradeStats:
    def __init__(self):
        self.users: Dict[int, UserTradeStats] = {}

    def add_trade(self, user_id: int, trade_item: Union[Chip, NaviCustPart]):
        if user_id not in self.users:
            self.users[user_id] = UserTradeStats(user_id)
        self.users[user_id].add_trade(trade_item)

    def get_total_trade_count(self) -> int:
        total = 0
        for user in self.users.values():
            total += user.get_total_trade_count()
        return total

    def get_total_user_count(self) -> int:
        return len(self.users)

    def get_users_by_trade_count(self) -> List[UserTradeStats]:
        all_users = self.users.values()
        sorted_users = sorted(all_users, key=lambda user: user.get_total_trade_count(), reverse=True)
        return sorted_users

    def get_trades_by_trade_count(self) -> List[Tuple[Union[Chip, NaviCustPart], int]]:
        all_items: Dict[Union[Chip, NaviCustPart], int] = collections.defaultdict(int)
        for user in self.users.values():
            for trade_item in user.trades:
                all_items[trade_item] += user.trades[trade_item]

        item_tuples = [(item, all_items[item]) for item in all_items]
        return sorted(item_tuples, key=lambda chip_tuple: chip_tuple[1], reverse=True)


class TradeManager:
    def __init__(
        self,
        server: Tuple[str, int],
        request_queue: multiprocessing.Queue[Optional[TradeCommand]],
        image_send_queue: multiprocessing.JoinableQueue[Optional[RoomCodeMessage]],
        message_queue: multiprocessing.SimpleQueue[Optional[DiscordMessageReplyRequest]],
    ):
        self.server = server
        self._queue_lock = multiprocessing.RLock()
        self._queued_trades: multiprocessing.Queue[Optional[RequestCommand]] = multiprocessing.Queue()
        self._request_queued = multiprocessing.Condition()

        self._current_userid = multiprocessing.Value("Q")
        self._cancel_trade_for_userid = multiprocessing.Value("Q")
        self._trade_cancelled = multiprocessing.Event()
        self._screencap_requested = multiprocessing.Event()
        self._screencap_requested.set()

        self.request_queue = request_queue
        self.image_send_queue = image_send_queue
        self.message_queue = message_queue

        self._bot_stats = self.bot_stats

        self._commands_process: Optional[multiprocessing.Process] = None
        self._trade_queue_process: Optional[multiprocessing.Process] = None

        with open(os.path.join(os.path.dirname(__file__), "common_items.json"), "r") as f:
            self.common_items = set(json.load(f))

        multiprocessing.log_to_stderr(logging.DEBUG)

    @property
    def bot_stats(self) -> BotTradeStats:
        try:
            with open("bot_stats.pkl", "rb") as f:
                return pickle.load(f)
        except Exception:
            return BotTradeStats()

    def start_processing(self):
        completion_recv, completion_send = multiprocessing.Pipe(duplex=False)
        cancel_recv, cancel_send = multiprocessing.Pipe(duplex=False)

        p1 = multiprocessing.Process(
            target=self.process_commands,
            args=(self.request_queue, self.message_queue, completion_recv, cancel_send),
            daemon=True,
        )
        p2 = multiprocessing.Process(
            target=self.process_trade_queue,
            args=(self.image_send_queue, self.message_queue, completion_send, cancel_recv),
            daemon=True,
        )
        p1.start()
        p2.start()
        self._commands_process = p1
        self._trade_queue_process = p2

    def stop(self):
        self.request_queue.put(None)
        self._commands_process.join()
        self._trade_queue_process.join()

    def process_cancellation(
        self,
        command: CancelCommand,
        message_queue: multiprocessing.SimpleQueue[DiscordMessageReplyRequest],
        cached_queue: Dict[int, RequestCommand],
        cancel_send: Any,
    ) -> None:
        logger.info(f"Cancelling trade for {command.user_name}")

        cancelled_queue = False
        with self._queue_lock:
            try:
                cached_queue.pop(command.user_id)
                cancel_send.send(command.user_id)

                cancelled_queue = True
                logger.debug("Removed user request from queue")
            except KeyError:
                logger.debug("User request not in queue")

            # Two scenarios:
            # 1. currently working on it
            # 2. Might have just finished it

            # If working on it, after waiting on the event, the userid is set to 0.
            # If it was just finished, userid should still be set.
            with self._cancel_trade_for_userid.get_lock():
                self._cancel_trade_for_userid.value = command.user_id
                self._trade_cancelled.clear()
            logger.debug("Waiting on trade cancelled event")
            self._trade_cancelled.wait()

            with self._cancel_trade_for_userid.get_lock():
                if self._cancel_trade_for_userid.value == 0:
                    logger.debug("User id value reset to 0, in-progress trade cancelled")
                    message_request = DiscordMessageReplyRequest(
                        command.discord_context, "Successfully cancelled in-progress trade.", MessageReaction.OK
                    )
                elif cancelled_queue:
                    logger.debug("User id value not reset but request removed from queue")
                    self._cancel_trade_for_userid.value = 0
                    message_request = DiscordMessageReplyRequest(
                        command.discord_context, "You don't have any queued trades.", MessageReaction.ERROR
                    )
                else:
                    logger.debug("User id value not reset and no request in queue")
                    self._cancel_trade_for_userid.value = 0
                    message_request = DiscordMessageReplyRequest(
                        command.discord_context, "Successfully cancelled queued trade.", MessageReaction.ERROR
                    )
                self._trade_cancelled.clear()

            message_queue.put(message_request)

    def process_clear_queue_request(
        self,
        command: ClearQueueCommand,
        message_queue: multiprocessing.SimpleQueue[DiscordMessageReplyRequest],
        cached_queue: Dict[int, RequestCommand],
        cancel_send: Any,
    ):
        with self._queue_lock:
            for user_id in cached_queue:
                trade_request = cached_queue[user_id]
                logger.debug(f"Removing request from queue: {trade_request.user_name} - {trade_request.trade_item}")
                cancel_send.send(user_id)
        cached_queue.clear()
        message_queue.put(DiscordMessageReplyRequest(command.discord_context, None, MessageReaction.OK))

    def process_trade_request(
        self,
        command: RequestCommand,
        message_queue: multiprocessing.SimpleQueue[DiscordMessageReplyRequest],
        cached_queue: Dict[int, RequestCommand],
    ) -> None:
        with self._queue_lock:
            if command.user_id in cached_queue:
                request = cached_queue[command.user_id]
                message_queue.put(
                    DiscordMessageReplyRequest(
                        command.discord_context,
                        f"You already have a pending request for `{request.trade_item}`",
                        MessageReaction.ERROR,
                    )
                )
            elif len(cached_queue) > 20 and str(command.trade_item) in self.common_items:
                message_queue.put(
                    DiscordMessageReplyRequest(
                        command.discord_context,
                        f"{command.trade_item} cannot be requested when there are more than 20 people in the queue. Try asking someone to dupe it for you!",
                        MessageReaction.ERROR,
                    )
                )
            else:
                cached_queue[command.user_id] = command
                self._queued_trades.put(command)
                message_queue.put(DiscordMessageReplyRequest(command.discord_context, None, MessageReaction.OK))

    def process_list_queue_request(
        self,
        command: ListQueueCommand,
        message_queue: multiprocessing.SimpleQueue[DiscordMessageReplyRequest],
        cached_queue: Dict[int, RequestCommand],
    ) -> None:
        if len(cached_queue) == 0:
            message_queue.put(
                DiscordMessageReplyRequest(command.discord_context, "There are no requests waiting in the queue.", None)
            )
        else:
            current_userid = self._current_userid.value

            embed = discord.Embed(title="Current queue")
            lines = []
            count = 0
            in_progress = None
            for _, request in cached_queue.items():
                if count >= 10:
                    break
                if current_userid == request.user_id:
                    in_progress = request
                else:
                    count += 1
                    lines.append(f"{count}. {request.user_name} ({request.user_id}) - {request.trade_item}")

            embed.add_field(
                name="In progress",
                value=f"{in_progress.user_name} ({in_progress.user_id}) - {in_progress.trade_item}"
                if in_progress
                else "No one",
            )
            embed.add_field(name="Queue", value="\n".join(lines) if lines else "No queued trades", inline=False)
            embed.set_footer(text=f"Total requests in queue: {len(cached_queue)}")
            message_queue.put(DiscordMessageReplyRequest(command.discord_context, embed.to_dict(), None))

    def process_commands(
        self,
        request_queue: multiprocessing.Queue[TradeCommand],
        message_queue: multiprocessing.SimpleQueue[DiscordMessageReplyRequest],
        completion_recv: Any,
        cancel_send: Any,
    ):
        cached_queue: Dict[int, RequestCommand] = {}

        try:
            with open("queue.pkl", "rb") as f:
                cached_queue = pickle.load(f)
                for _, command in cached_queue.items():
                    self._queued_trades.put(command)
            os.unlink("queue.pkl")
        except FileNotFoundError:
            pass

        while True:
            try:
                command = None
                while command is None:
                    try:
                        command = request_queue.get(timeout=1.0)
                        if command is None:
                            print("Shutdown requested, notifying other process")
                            self._queued_trades.put(None)
                            return
                    except queue.Empty:
                        pass

                    # Process all completion notifications and remove them from our cached copy of the queue
                    while completion_recv.poll():
                        user_id = completion_recv.recv()
                        try:
                            completed = cached_queue.pop(user_id)
                            print(f"Completed trade for {user_id}: {completed.trade_item}")
                            self._bot_stats.add_trade(user_id, completed.trade_item)

                            with open("bot_stats.pkl", "wb") as f:
                                pickle.dump(self._bot_stats, f)
                        except KeyError:
                            print(f"Tried to pop {user_id} from cached queue but it didn't exist!")

                if isinstance(command, CancelCommand):
                    self.process_cancellation(command, message_queue, cached_queue, cancel_send)
                elif isinstance(command, RequestCommand):
                    self.process_trade_request(command, message_queue, cached_queue)
                elif isinstance(command, ListQueueCommand):
                    self.process_list_queue_request(command, message_queue, cached_queue)
                elif isinstance(command, ClearQueueCommand):
                    self.process_clear_queue_request(command, message_queue, cached_queue, cancel_send)
                elif isinstance(command, PauseQueueCommand):
                    with self._queue_lock:
                        with open("queue.pkl", "wb") as f:
                            pickle.dump(cached_queue, f)
                        message_queue.put(DiscordMessageReplyRequest(command.discord_context, None, MessageReaction.OK))
                        command = request_queue.get()
                        while not isinstance(command, PauseQueueCommand):
                            command = request_queue.get()
                        try:
                            os.unlink("queue.pkl")
                        except FileNotFoundError:
                            pass
                    message_queue.put(DiscordMessageReplyRequest(command.discord_context, None, MessageReaction.OK))
                elif isinstance(command, ScreenCaptureCommand):
                    self._screencap_requested.clear()
                    self._screencap_requested.wait()
                else:
                    raise RuntimeError(f"Unknown command: {command}")

            except Exception:
                import traceback

                traceback.print_exc()

    def process_trade_queue(
        self,
        image_send_queue: multiprocessing.JoinableQueue[RoomCodeMessage],
        message_queue: multiprocessing.SimpleQueue[DiscordMessageReplyRequest],
        completion_send: Any,
        cancel_recv: Any,
    ):
        with SocketSink(self.server[0], self.server[1]) as sink:
            controller = Controller(sink)
            trader = AutoTrader(controller)

            cancelled_requests = set()
            # Let the screen pop up if needed
            controller.press_button(Button.Nothing, wait_ms=2000)
            if (
                image_processing.run_tesseract_line(image_processing.capture(), (1000, 1000), (460, 460))
                == "Controller Not Connecting"
            ):
                print("Found controller connect screen, connecting")
                controller.press_button(Button.L + Button.R, hold_ms=100, wait_ms=2000)
                controller.press_button(Button.A, hold_ms=100, wait_ms=2000)

            while True:
                try:
                    while True:
                        # Receive all cancellation requests
                        while cancel_recv.poll():
                            cancelled_requests.add(cancel_recv.recv())

                        # Get screen capture if requested
                        if not self._screencap_requested.is_set():
                            img = image_processing.convert_image_to_png_bytestring(
                                image_processing.capture(convert=True)
                            )
                            # image_send_queue.put(DiscordMessageReplyRequest(command.discord_context, None, MessageReaction.OK))
                            self._screencap_requested.set()

                        try:
                            with self._queue_lock, self._cancel_trade_for_userid.get_lock():
                                current_trade = self._queued_trades.get_nowait()

                                if current_trade is None:
                                    print("Shutdown requested, exiting")
                                    return
                                # Process cancellation requests
                                elif current_trade.user_id in cancelled_requests:
                                    cancelled_requests.remove(current_trade.user_id)
                                    continue

                                self._cancel_trade_for_userid.value = 0
                                break
                        except queue.Empty:
                            # Keep the Switch awake
                            trader.x()
                            time.sleep(0.1)

                    while True:
                        self._current_userid.value = current_trade.discord_context.user_id
                        if isinstance(current_trade.trade_item, Chip):
                            result, message = trader.trade_chip(
                                current_trade.discord_context,
                                current_trade.trade_item,
                                self._cancel_trade_for_userid,
                                self._trade_cancelled,
                                image_send_queue,
                            )
                        else:
                            result, message = trader.trade_ncp(
                                current_trade.discord_context,
                                current_trade.trade_item,
                                self._cancel_trade_for_userid,
                                self._trade_cancelled,
                                image_send_queue,
                            )
                        if result == TradeResult.UnexpectedState:
                            embed = discord.Embed(title="Trade failure!", description=message, color=0xFF0000)
                            embed.add_field(name="Last inputs", value="\n".join(trader.get_last_inputs()), inline=False)
                            message_dict = embed.to_dict()
                            image = image_processing.capture(convert=True)
                            png_image = image_processing.convert_image_to_png_bytestring(image)
                            message_dict["image"] = png_image
                            message_queue.put(
                                DiscordMessageReplyRequest(current_trade.discord_context, message_dict, None)
                            )
                        elif result == TradeResult.CommunicationError:
                            message_queue.put(DiscordMessageReplyRequest(current_trade.discord_context, message, None))
                            continue
                        elif result != TradeResult.Success and result != TradeResult.Cancelled:
                            message_queue.put(DiscordMessageReplyRequest(current_trade.discord_context, message, None))
                        break

                    # Notify the other worker thread of completion
                    self._current_userid.value = 0
                    completion_send.send(current_trade.discord_context.user_id)

                except Exception:
                    import traceback

                    traceback.print_exc()
