from __future__ import annotations

import collections
import multiprocessing
import pickle
import queue
import time
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from auto_trader import AutoTrader, DiscordContext, RoomCodeMessage, TradeResult
from bn_automation.controller import Controller
from bn_automation.controller.sinks import SocketSink
from chip import Chip


class MessageReaction(Enum):
    OK = "✅"
    ERROR = "❌"


class TradeCommand:
    REQUEST_CHIP = 1
    CANCEL_REQUEST = 2
    LIST_QUEUE = 3
    CLEAR_QUEUE = 4
    PAUSE_QUEUE = 5

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
    def __init__(self, discord_context: DiscordContext, chip: Chip):
        super().__init__(command=TradeCommand.REQUEST_CHIP, discord_context=discord_context, chip=chip)

    @property
    def chip(self) -> Chip:
        return self.data["chip"]


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


class DiscordMessageReplyRequest:
    def __init__(self, discord_context: DiscordContext, message: Optional[str], reaction: Optional[MessageReaction]):
        self.discord_context = discord_context
        self.message = message
        self.reaction = reaction


class UserTradeStats:
    def __init__(self, user_id: int):
        self.user_id = user_id
        self.chips: Dict[Chip, int] = collections.defaultdict(int)

    def add_trade(self, chip: Chip):
        self.chips[chip] += 1

    def get_total_trade_count(self) -> int:
        total = 0
        for qty in self.chips.values():
            total += qty
        return total


class BotTradeStats:
    def __init__(self):
        self.users = {}

    def add_trade(self, user_id: int, chip: Chip):
        if user_id not in self.users:
            self.users[user_id] = UserTradeStats(user_id)
        self.users[user_id].add_trade(chip)

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

    def get_chips_by_trade_count(self) -> List[Tuple[Chip, int]]:
        all_chips: Dict[Chip, int] = collections.defaultdict(int)
        for user in self.users.values():
            for chip in user.chips:
                all_chips[chip] += user.chips[chip]

        chip_tuples = [(chip, all_chips[chip]) for chip in all_chips]
        return sorted(chip_tuples, key=lambda chip_tuple: chip_tuple[1], reverse=True)


class TradeManager:
    def __init__(
        self,
        request_queue: multiprocessing.SimpleQueue[TradeCommand],
        room_code_queue: multiprocessing.JoinableQueue[RoomCodeMessage],
        message_queue: multiprocessing.SimpleQueue[DiscordMessageReplyRequest],
    ):
        self._queue_lock = multiprocessing.RLock()
        self._queued_trades: multiprocessing.Queue[RequestCommand] = multiprocessing.Queue()
        self._request_queued = multiprocessing.Condition()

        self._current_userid = multiprocessing.Value("Q")
        self._cancel_trade_for_userid = multiprocessing.Value("Q")
        self._trade_cancelled = multiprocessing.Event()

        self.request_queue = request_queue
        self.room_code_queue = room_code_queue
        self.message_queue = message_queue

        try:
            with open("bot_stats.pkl", "rb") as f:
                self.bot_stats = pickle.load(f)
        except Exception:
            self.bot_stats = BotTradeStats()

    def start_processing(self):
        completion_recv, completion_send = multiprocessing.Pipe(duplex=False)
        cancel_recv, cancel_send = multiprocessing.Pipe(duplex=False)

        multiprocessing.Process(
            target=self.process_commands,
            args=(self.request_queue, self.message_queue, completion_recv, cancel_send),
            daemon=True,
        ).start()
        multiprocessing.Process(
            target=self.process_trade_queue,
            args=(self.room_code_queue, self.message_queue, completion_send, cancel_recv),
            daemon=True,
        ).start()

    def process_cancellation(
        self,
        command: CancelCommand,
        message_queue: multiprocessing.SimpleQueue[DiscordMessageReplyRequest],
        cached_queue: Dict[int, RequestCommand],
        cancel_send: Any,
    ) -> None:
        print(f"Cancelling trade for {command.user_name}")

        with self._queue_lock:
            try:
                # If this succeeds, then we're not actively working on it
                cached_queue.pop(command.user_id)
                cancel_send.send(command.user_id)

                message_queue.put(
                    DiscordMessageReplyRequest(
                        command.discord_context, "Successfully cancelled queued trade.", MessageReaction.OK
                    )
                )
                return
            except KeyError:
                # Two scenarios:
                # 1. currently working on it
                # 2. Might have just finished it

                # If working on it, after waiting on the event, the userid is set to 0.
                # If it was just finished, userid should still be set.
                with self._cancel_trade_for_userid.get_lock():
                    self._cancel_trade_for_userid.value = command.user_id
                    self._trade_cancelled.clear()
                self._trade_cancelled.wait()

                with self._cancel_trade_for_userid.get_lock():
                    if self._cancel_trade_for_userid.value == 0:
                        message_request = DiscordMessageReplyRequest(
                            command.discord_context, "Successfully cancelled in-progress trade.", MessageReaction.OK
                        )
                    else:
                        self._cancel_trade_for_userid.value = 0
                        message_request = DiscordMessageReplyRequest(
                            command.discord_context, "You don't have any queued trades.", MessageReaction.ERROR
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
            for user_id, trade_request in cached_queue:
                print(f"Removing request from queue: {trade_request.user_name} - {trade_request.chip}")
                cancel_send.send(user_id)
        cached_queue.clear()
        # message_queue.put(DiscordMessageReplyRequest(command.discord_context, "Successfully cleared queue", MessageReaction.OK))
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
                        f"You already have a pending request for `{request.chip.name} {request.chip.code}`",
                        MessageReaction.ERROR,
                    )
                )
            else:
                cached_queue[command.user_id] = command
                self._queued_trades.put(command)
                """
                message_queue.put(
                    DiscordMessageReplyRequest(
                        command.discord_context,
                        f"Your request for `{command.chip.name} {command.chip.code}` has been added.",
                        MessageReaction.OK
                    )
                )
                """
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
            count = 0
            lines = ["```"]
            for _, request in cached_queue.items():
                count += 1
                if count > 10:
                    break
                if current_userid == request.user_id:
                    lines.append(
                        f"{count}. [IN PROGRESS] {request.user_name} ({request.user_id}) - {request.chip.name} {request.chip.code}"
                    )
                else:
                    lines.append(
                        f"{count}. {request.user_name} ({request.user_id}) - {request.chip.name} {request.chip.code}"
                    )
            lines.append("```")
            lines.append(f"Total requests in queue: {len(cached_queue)}")
            message_queue.put(DiscordMessageReplyRequest(command.discord_context, "\n".join(lines), None))

    def process_commands(
        self,
        request_queue: multiprocessing.SimpleQueue[TradeCommand],
        message_queue: multiprocessing.SimpleQueue[DiscordMessageReplyRequest],
        completion_recv: Any,
        cancel_send: Any,
    ):
        cached_queue: Dict[int, RequestCommand] = {}
        try:
            with open("queue.pkl", "rb") as f:
                saved_requests = pickle.load(f)
        except Exception:
            saved_requests = {}

        for saved_request in saved_requests.values():
            cached_queue[saved_request.user_id] = saved_request
            self._queued_trades.put(saved_request)

        while True:
            try:
                command = request_queue.get()

                # Process all completion notifications and remove them from our cached copy of the queue
                while completion_recv.poll():
                    user_id = completion_recv.recv()
                    try:
                        completed = cached_queue.pop(user_id)
                        self.bot_stats.add_trade(user_id, completed.chip)

                        with open("bot_stats.pkl", "wb") as f:
                            pickle.dump(self.bot_stats, f)
                    except KeyError:
                        raise RuntimeError(f"Tried to pop {user_id} from cached queue but it didn't exist!")

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
                        message_queue.put(DiscordMessageReplyRequest(command.discord_context, None, MessageReaction.OK))
                        while not isinstance(request_queue.get(), PauseQueueCommand):
                            pass
                    message_queue.put(DiscordMessageReplyRequest(command.discord_context, None, MessageReaction.OK))
                else:
                    raise RuntimeError(f"Unknown command: {command}")

                with open("queue.pkl", "wb") as f:
                    pickle.dump(cached_queue, f)
            except Exception:
                import traceback

                traceback.print_exc()

    def process_trade_queue(
        self,
        room_code_queue: multiprocessing.JoinableQueue[RoomCodeMessage],
        message_queue: multiprocessing.SimpleQueue[DiscordMessageReplyRequest],
        completion_send: Any,
        cancel_recv: Any,
    ):
        with SocketSink("raspberrypi.local", 3000) as sink:
            controller = Controller(sink)
            trader = AutoTrader(controller)

            cancelled_requests = set()

            while True:
                try:
                    current_trade = None
                    while current_trade is None:
                        # Receive all cancellation requests
                        while cancel_recv.poll():
                            cancelled_requests.add(cancel_recv.recv())
                        try:
                            with self._queue_lock, self._cancel_trade_for_userid.get_lock():
                                current_trade = self._queued_trades.get_nowait()

                                # Process cancellation requests
                                if current_trade.user_id in cancelled_requests:
                                    cancelled_requests.remove(current_trade.user_id)
                                    current_trade = None
                                    continue

                                self._cancel_trade_for_userid.value = 0
                        except queue.Empty:
                            time.sleep(0.1)

                    self._current_userid.value = current_trade.discord_context.user_id
                    result, message = trader.trade(
                        current_trade.discord_context,
                        current_trade.chip,
                        self._cancel_trade_for_userid,
                        self._trade_cancelled,
                        room_code_queue,
                    )
                    if result != TradeResult.Success and result != TradeResult.Cancelled:
                        message_queue.put(DiscordMessageReplyRequest(current_trade.discord_context, message, None))

                    # Notify the other worker thread of completion
                    self._current_userid.value = 0
                    completion_send.send(current_trade.discord_context.user_id)

                except Exception:
                    import traceback

                    traceback.print_exc()
