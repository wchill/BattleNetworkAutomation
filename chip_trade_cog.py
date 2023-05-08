import asyncio
import io
import json
import os
import threading
from typing import Optional

import discord
from discord.ext import commands

from auto_trader import DiscordContext, RoomCodeMessage
from chip_list import ChipList
from trade_manager import (
    CancelCommand,
    ClearQueueCommand,
    DiscordMessageReplyRequest,
    ListQueueCommand,
    PauseQueueCommand,
    RequestCommand,
    TradeManager,
)

with open(os.path.join(os.path.dirname(__file__), "config.json"), "r") as f:
    config = json.load(f)
discord_config = config["discord"]

CHANNEL_IDS = {int(channel_id) for channel_id in discord_config["trade_channel_ids"]}


def in_channel_check(ctx: commands.Context):
    return ctx.channel.id in CHANNEL_IDS


in_channel = commands.check(in_channel_check)


class ChipTradeCog(commands.Cog, name="Chip Trade"):
    def __init__(self, bot: commands.Bot, trade_manager: TradeManager):
        self.bot = bot
        self.trade_manager = trade_manager

    @commands.Cog.listener()
    async def on_ready(self):
        threading.Thread(target=self.handle_message_requests, daemon=True).start()
        threading.Thread(target=self.handle_room_code_requests, daemon=True).start()

    async def reply_to_command(self, message_request: DiscordMessageReplyRequest):
        discord_channel = self.bot.get_channel(message_request.discord_context.channel_id)
        discord_message = await discord_channel.fetch_message(message_request.discord_context.message_id)

        if message_request.reaction:
            await discord_message.add_reaction(message_request.reaction.value)

        if message_request.message:
            await discord_message.reply(message_request.message)

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
        chip = room_code_request.chip
        await user.send(
            f"Your `{chip.name} {chip.code}` is ready! You have 180 seconds to join",
            silent=False,
            file=discord.File(fp=io.BytesIO(room_code_request.image), filename="roomcode.png"),
        )

    def handle_room_code_requests(self):
        while True:
            try:
                room_code_request = self.trade_manager.room_code_queue.get()
                asyncio.run_coroutine_threadsafe(self.message_room_code(room_code_request), self.bot.loop)
                self.trade_manager.room_code_queue.task_done()
            except Exception:
                import traceback

                traceback.print_exc()

    @commands.command()
    @in_channel
    async def request(self, ctx: commands.Context, chip_name: str, chip_code: str):
        chip = ChipList.get_chip(chip_name, chip_code)
        if chip is None:
            await ctx.message.reply("That's not a tradable chip. Make sure to use in-game spelling.")
        else:
            self.trade_manager.request_queue.put(RequestCommand(DiscordContext.create(ctx), chip))

    @commands.command()
    @in_channel
    async def cancel(self, ctx: commands.Context, user_id: Optional[int] = None):
        if user_id is not None:
            if not await self.bot.is_owner(ctx.author):
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
        self.trade_manager.request_queue.put(ListQueueCommand(DiscordContext.create(ctx)))

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

    @commands.command()
    @in_channel
    async def topchips(self, ctx: commands.Context):
        top_chips = self.trade_manager.bot_stats.get_chips_by_trade_count()
        lines = ["```"]
        count = 0
        for chip, qty in top_chips:
            count += 1
            if count >= 20:
                break
            lines.append(f"{qty} - {chip.name} {chip.code}")
        lines.append("```")
        await ctx.message.reply("\n".join(lines))

    @commands.command()
    @in_channel
    async def topusers(self, ctx: commands.Context):
        top_users = self.trade_manager.bot_stats.get_users_by_trade_count()
        lines = ["```"]
        count = 0
        for user in top_users:
            count += 1
            if count >= 20:
                break
            discord_user = await self.bot.fetch_user(user.user_id)
            if discord_user is not None:
                lines.append(
                    f"{user.get_total_trade_count()} - {discord_user.display_name or discord_user.name or discord_user.id}"
                )
        lines.append("```")
        await ctx.message.reply("\n".join(lines))

    @commands.command()
    @in_channel
    async def tradecount(self, ctx: commands.Context):
        await ctx.message.reply(
            f"I've recorded trades for {self.trade_manager.bot_stats.get_total_trade_count()} chips to {self.trade_manager.bot_stats.get_total_user_count()} users."
        )
