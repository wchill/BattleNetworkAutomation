import asyncio
import concurrent.futures
import io
import json
import multiprocessing
import os
import pickle
import threading
import time
from typing import Optional

import discord
from discord.ext import commands, tasks

from auto_trader import DiscordContext, RoomCodeMessage
from bn_automation.controller import Button, DPad
from chip_list import ChipList
from navicust_part_list import NaviCustPartList
from trade_manager import (
    CancelCommand,
    ClearQueueCommand,
    DiscordMessageReplyRequest,
    ListQueueCommand,
    LoadQueueCommand,
    PauseQueueCommand,
    RequestCommand,
    TradeManager,
)
from utils import MessageReaction

with open(os.path.join(os.path.dirname(__file__), "config.json"), "r") as f:
    config = json.load(f)
discord_config = config["discord"]

CHANNEL_IDS = {int(channel_id) for channel_id in discord_config["trade_channel_ids"]}
QUEUE_MESSAGE_ID = discord_config["queue_message_id"]
QUEUE_MESSAGE_CHANNEL = int(discord_config["queue_message_channel"])


def in_channel_check(ctx: commands.Context):
    return ctx.channel.id in CHANNEL_IDS


in_channel = commands.check(in_channel_check)


class TradeCog(commands.Cog, name="Trade"):
    def __init__(self, bot: commands.Bot, trade_manager: TradeManager):
        self.bot = bot
        self.trade_manager = trade_manager
        self.queue_message_id = None
        self._message_req_thread = None
        self._image_req_thread = None

        self._queue_message = None

    @tasks.loop(seconds=60)
    async def change_status(self):
        # url="https://discord.com/invite/u9ZRNTDbcz",
        if self.bot.is_ready():
            await self.bot.change_presence(
                status=discord.Status.online,
                activity=discord.Streaming(
                    name=f"{self.trade_manager.bot_stats.get_total_trade_count()} trades to {self.trade_manager.bot_stats.get_total_user_count()} users",
                    url="https://discord.com/invite/u9ZRNTDbcz",
                ),
            )

    @commands.Cog.listener()
    async def on_ready(self):
        print("Trade cog successfully loaded")

        global QUEUE_MESSAGE_ID, config
        channel = await self.bot.fetch_channel(QUEUE_MESSAGE_CHANNEL)
        if QUEUE_MESSAGE_ID is None:
            self._queue_message = await channel.send("This will be replaced with the queue.")
            QUEUE_MESSAGE_ID = self._queue_message.id
            config["discord"]["queue_message_id"] = QUEUE_MESSAGE_ID
            with open(os.path.join(os.path.dirname(__file__), "config.json"), "w") as f:
                json.dump(config, f)
        else:
            QUEUE_MESSAGE_ID = int(QUEUE_MESSAGE_ID)
            self._queue_message = await channel.fetch_message(QUEUE_MESSAGE_ID)
        self._queue_update_thread.start()

    async def cog_load(self) -> None:
        self._message_req_thread = threading.Thread(target=self.handle_message_requests, daemon=True)
        self._image_req_thread = threading.Thread(target=self.handle_image_message_requests, daemon=True)
        self._queue_update_thread = threading.Thread(target=self.handle_queue_updates, daemon=True)
        self._message_req_thread.start()
        self._image_req_thread.start()
        self.trade_manager.start_processing()
        self.change_status.start()

    async def cog_unload(self) -> None:
        print("Unloading cog")
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        await self.bot.loop.run_in_executor(executor, self.trade_manager.stop)

    async def reply_to_command(self, message_request: DiscordMessageReplyRequest):
        discord_channel = self.bot.get_channel(message_request.discord_context.channel_id)
        discord_message = await discord_channel.fetch_message(message_request.discord_context.message_id)

        if message_request.reaction:
            await discord_message.add_reaction(message_request.reaction.value)

        if isinstance(message_request.message, str):
            await discord_message.reply(message_request.message)
        elif isinstance(message_request.message, dict):
            if "image" in message_request.message:
                image = message_request.message.pop("image")
            else:
                image = None
            embed = discord.Embed.from_dict(message_request.message)
            attach = discord.File(fp=io.BytesIO(image), filename="screencapture.png")
            embed.set_image(url="attachment://screencapture.png")

            if image is not None:
                await discord_message.reply(embed=embed, file=attach)
            else:
                await discord_message.reply(embed=embed)

    def handle_queue_updates(self):
        last_update_time = 0
        while True:
            try:
                cached_queue, current_userid = self.trade_manager.queue_update_queue.get()

                if time.time() - last_update_time > 30:
                    last_update_time = time.time()
                    lines = []
                    count = 0
                    in_progress = None
                    for _, request in cached_queue.items():
                        if count >= 30:
                            break
                        if current_userid == request.user_id:
                            in_progress = request
                        else:
                            count += 1
                            lines.append(f"{count}. {request.user_name} ({request.user_id}) - {request.trade_item}")

                    embed = discord.Embed(
                        title=f"Current queue ({len(cached_queue)})",
                        description="\n".join(lines) if lines else "No queued trades",
                    )
                    embed.add_field(
                        name="In progress",
                        value=f"{in_progress.user_name} ({in_progress.user_id}) - {in_progress.trade_item}"
                        if in_progress
                        else "No one",
                    )
                    embed.set_footer(text="The queue is refreshed every 30 seconds")
                    asyncio.run_coroutine_threadsafe(self._queue_message.edit(content="", embed=embed), self.bot.loop)
            except Exception:
                import traceback

                traceback.print_exc()

    def handle_message_requests(self):
        while True:
            try:
                message_request = self.trade_manager.message_queue.get()
                asyncio.run_coroutine_threadsafe(self.reply_to_command(message_request), self.bot.loop)
            except Exception:
                import traceback

                traceback.print_exc()

    async def message_room_code(self, room_code_request: RoomCodeMessage):
        user = await self.bot.fetch_user(room_code_request.discord_context.user_id)
        obj = room_code_request.obj
        await user.send(
            f"Your `{str(obj)}` is ready! You have 180 seconds to join",
            silent=False,
            file=discord.File(fp=io.BytesIO(room_code_request.image), filename="roomcode.png"),
        )

    async def message_screenshot(self, message_request: DiscordMessageReplyRequest):
        user = await self.bot.fetch_user(self.bot.owner_id)
        await user.send(
            f"Screencapture",
            silent=False,
            file=discord.File(fp=io.BytesIO(message_request.image), filename="screencapture.png"),
        )

    def handle_image_message_requests(self):
        while True:
            try:
                image_request = self.trade_manager.image_send_queue.get()
                if isinstance(image_request, RoomCodeMessage):
                    asyncio.run_coroutine_threadsafe(self.message_room_code(image_request), self.bot.loop)
            except Exception:
                import traceback

                traceback.print_exc()

            self.trade_manager.image_send_queue.task_done()

    @commands.command()
    @in_channel
    async def request(self, ctx: commands.Context, item_name: str, item_variant: str):
        chip = ChipList.get_tradable_chip(item_name, item_variant)
        ncp = NaviCustPartList.get_ncp(item_name, item_variant)
        if chip is None and ncp is None:
            await ctx.message.add_reaction(MessageReaction.ERROR.value)
            await ctx.message.reply("That's not a tradable chip or NaviCust part. Make sure to use in-game spelling.")
        else:
            self.trade_manager.request_queue.put(RequestCommand(DiscordContext.create(ctx), chip or ncp))

    @commands.command()
    @commands.is_owner()
    @in_channel
    async def requestfor(self, ctx: commands.Context, user: discord.User, item_name: str, item_variant: str):
        chip = ChipList.get_tradable_chip(item_name, item_variant)
        ncp = NaviCustPartList.get_ncp(item_name, item_variant)
        if chip is None and ncp is None:
            await ctx.message.add_reaction(MessageReaction.ERROR.value)
            await ctx.message.reply("That's not a tradable chip or NaviCust part. Make sure to use in-game spelling.")
        else:
            context = DiscordContext(
                user.display_name,
                user.id,
                ctx.message.id,
                ctx.channel.id,
            )
            self.trade_manager.request_queue.put(RequestCommand(context, chip or ncp))

    @commands.command()
    @in_channel
    async def cancel(self, ctx: commands.Context, user_id: Optional[int] = None):
        if not await self.bot.is_owner(ctx.author):
            await ctx.message.add_reaction(MessageReaction.ERROR.value)
            await ctx.message.reply("This command is temporarily disabled.")
            return

        if user_id is not None:
            if not await self.bot.is_owner(ctx.author):
                await ctx.message.add_reaction(MessageReaction.ERROR.value)
                await ctx.message.reply("You can only cancel your own requests.")
            else:
                self.trade_manager.request_queue.put(
                    CancelCommand(DiscordContext(ctx.author.display_name, user_id, ctx.message.id, ctx.channel.id))
                )
        else:
            self.trade_manager.request_queue.put(CancelCommand(DiscordContext.create(ctx)))

    @commands.command()
    @in_channel
    async def queue(self, ctx: commands.Context):
        if await self.bot.is_owner(ctx.author):
            self.trade_manager.request_queue.put(ListQueueCommand(DiscordContext.create(ctx)))
        else:
            await ctx.message.add_reaction(MessageReaction.ERROR.value)
            await ctx.message.reply("Please check <#1106460288124985384> for the current queue.")

    @commands.command()
    @in_channel
    @commands.is_owner()
    async def loadqueue(self, ctx: commands.Context):
        self.trade_manager.request_queue.put(LoadQueueCommand(DiscordContext.create(ctx)))

    @commands.command()
    @in_channel
    @commands.is_owner()
    async def listsavedqueue(self, ctx: commands.Context):
        with open("queue.pkl", "rb") as f:
            q = pickle.load(f)
        lines = ["```"]
        for user_id, trade_command in q.items():
            lines.append(f"{user_id}: {trade_command.trade_item}")
        lines.append("```")
        await ctx.reply("\n".join(lines))

    @commands.command()
    @in_channel
    @commands.is_owner()
    async def clearqueue(self, ctx: commands.Context):
        self.trade_manager.request_queue.put(ClearQueueCommand(DiscordContext.create(ctx)))

    @commands.command()
    @in_channel
    @commands.is_owner()
    async def pause(self, ctx: commands.Context):
        self.trade_manager.request_queue.put(PauseQueueCommand(DiscordContext.create(ctx)))

    """@commands.command()
    @commands.is_owner()
    async def screencapture(self, ctx: commands.Context):
        self.trade_manager.request_queue.put(ScreenCaptureCommand(DiscordContext.create(ctx)))"""

    @commands.command()
    @in_channel
    async def toptrades(self, ctx: commands.Context):
        top_items = self.trade_manager.bot_stats.get_trades_by_trade_count()
        lines = []
        count = 0
        for trade_item, qty in top_items:
            count += 1
            if count > 20:
                break
            lines.append(f"{count}. {trade_item} x{qty}")

        embed = discord.Embed(title="Top trades")
        embed.add_field(name="Top trades", value="\n".join(lines), inline=False)
        await ctx.message.reply(embed=embed)

    @commands.command()
    @in_channel
    async def topusers(self, ctx: commands.Context):
        top_users = self.trade_manager.bot_stats.get_users_by_trade_count()

        lines = []
        count = 0
        for user in top_users:
            count += 1
            if count >= 20:
                break
            discord_user = await self.bot.fetch_user(user.user_id)
            if discord_user is not None:
                lines.append(
                    f"{count}. {discord_user.display_name or discord_user.name or discord_user.id} - {user.get_total_trade_count()} trades"
                )
            else:
                if discord_user is not None:
                    lines.append(f"{count}. {user.user_id} - {user.get_total_trade_count()} trades")

        embed = discord.Embed(title="Top users by trade count")
        embed.add_field(name="Top users", value="\n".join(lines), inline=False)
        embed.set_footer(text=f"{len(top_users)} users total")
        await ctx.message.reply(embed=embed)

    @commands.command()
    @in_channel
    async def trades(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        if member is None:
            user_id = ctx.author.id
        else:
            user_id = member.id
        user = self.trade_manager.bot_stats.users.get(user_id)
        if user is None:
            if member is None:
                await ctx.message.reply("You haven't made any trades.")
            else:
                await ctx.message.reply(f"{member.display_name} hasn't made any trades.")
            return

        discord_user = member or ctx.author
        lines = []
        count = 0
        for chip, qty in user.get_trades_by_trade_count():
            count += 1
            if count >= 20:
                break
            lines.append(f"{count}. {chip.name} {chip.code} x{qty}")

        embed = discord.Embed(title=f"{discord_user.display_name}'s trades")
        embed.add_field(name="Top trades", value="\n".join(lines), inline=False)
        embed.set_footer(text=f"{user.get_total_trade_count()} trades for {len(user.trades)} different things")
        await ctx.message.reply(embed=embed)

    @commands.command()
    @in_channel
    async def tradecount(self, ctx: commands.Context):
        await ctx.message.reply(
            f"I've recorded trades for {self.trade_manager.bot_stats.get_total_trade_count()} things to {self.trade_manager.bot_stats.get_total_user_count()} users."
        )

    @commands.command()
    @in_channel
    @commands.is_owner()
    async def control(self, ctx: commands.Context, buttons: str):
        input_list = buttons.split(",")
        converted_inputs = []

        all_buttons = {e.name.lower() for e in Button}
        all_dpads = {e.name.lower() for e in DPad}
        for x in input_list:
            lower_x = x.lower()
            if lower_x in all_dpads:
                converted_inputs.append(DPad[x.lower().capitalize()])
            elif lower_x in all_buttons:
                if lower_x == "zl" or lower_x == "zr":
                    x = x.upper()
                else:
                    x = x.lower().capitalize()
                converted_inputs.append(Button[x])
            else:
                await ctx.message.reply(f"Unknown input: {x}")
                return

        self.trade_manager.send_inputs(converted_inputs)
        await ctx.message.reply(f"Queued the inputs for execution")


async def setup(bot: commands.Bot) -> None:
    request_queue = multiprocessing.Queue()
    image_send_queue = multiprocessing.JoinableQueue()
    message_queue = multiprocessing.SimpleQueue()
    queue_update_queue = multiprocessing.SimpleQueue()
    # utils.wait_port("127.0.0.1", 3000)
    trade_manager = TradeManager(
        ("127.0.0.1", 3000), request_queue, image_send_queue, message_queue, queue_update_queue
    )
    await bot.add_cog(TradeCog(bot, trade_manager))
