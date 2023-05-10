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
from navicust_part_list import NaviCustPartList
from trade_manager import (
    CancelCommand,
    ClearQueueCommand,
    DiscordMessageReplyRequest,
    ListQueueCommand,
    PauseQueueCommand,
    RequestCommand,
    ScreenCaptureCommand,
    ScreenCaptureMessage,
    TradeManager,
)

with open(os.path.join(os.path.dirname(__file__), "config.json"), "r") as f:
    config = json.load(f)
discord_config = config["discord"]

CHANNEL_IDS = {int(channel_id) for channel_id in discord_config["trade_channel_ids"]}


def in_channel_check(ctx: commands.Context):
    return ctx.channel.id in CHANNEL_IDS


in_channel = commands.check(in_channel_check)


class TradeCog(commands.Cog, name="Trade"):
    def __init__(self, bot: commands.Bot, trade_manager: TradeManager):
        self.bot = bot
        self.trade_manager = trade_manager

    @commands.Cog.listener()
    async def on_ready(self):
        threading.Thread(target=self.handle_message_requests, daemon=True).start()
        threading.Thread(target=self.handle_image_message_requests, daemon=True).start()

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
        obj = room_code_request.obj
        await user.send(
            f"Your `{str(obj)}` is ready! You have 180 seconds to join",
            silent=False,
            file=discord.File(fp=io.BytesIO(room_code_request.image), filename="roomcode.png"),
        )

    async def message_screenshot(self, message_request: ScreenCaptureMessage):
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
                elif isinstance(image_request, ScreenCaptureMessage):
                    asyncio.run_coroutine_threadsafe(self.message_screenshot(image_request), self.bot.loop)
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
            await ctx.message.reply("That's not a tradable chip or NaviCust part. Make sure to use in-game spelling.")
        else:
            self.trade_manager.request_queue.put(RequestCommand(DiscordContext.create(ctx), chip or ncp))

    @commands.command()
    @in_channel
    async def cancel(self, ctx: commands.Context, user_id: Optional[int] = None):
        if not self.bot.is_owner(ctx.author):
            await ctx.message.reply("This command is temporarily disabled.")
            return

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
    @commands.is_owner()
    async def screencapture(self, ctx: commands.Context):
        self.trade_manager.request_queue.put(ScreenCaptureCommand(DiscordContext.create(ctx)))

    @commands.command()
    @in_channel
    async def toptrades(self, ctx: commands.Context):
        top_items = self.trade_manager.bot_stats.get_trades_by_trade_count()
        lines = ["```"]
        count = 0
        for trade_item, qty in top_items:
            count += 1
            if count >= 20:
                break
            lines.append(f"{qty} - {trade_item}")
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

        lines = ["```"]
        count = 0
        for chip, qty in user.get_trades_by_trade_count():
            count += 1
            if count >= 20:
                break
            lines.append(f"{qty} - {chip.name} {chip.code}")
        lines.append("```")
        lines.append(f"You've made {user.get_total_trade_count()} total trades for {len(user.chips)} different things.")
        await ctx.message.reply("\n".join(lines))

    @commands.command()
    @in_channel
    async def tradecount(self, ctx: commands.Context):
        await ctx.message.reply(
            f"I've recorded trades for {self.trade_manager.bot_stats.get_total_trade_count()} things to {self.trade_manager.bot_stats.get_total_user_count()} users."
        )
