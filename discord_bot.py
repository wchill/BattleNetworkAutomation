import asyncio
import io
import json
import os
import queue
import sys
import threading

import cv2 as cv
import discord
from discord.ext import commands

from auto_trader import AutoTrader, Chip, Code, FailureReason
from bn_automation.controller import Controller
from bn_automation.controller.sinks import SocketSink

with open(os.path.join(os.path.dirname(__file__), "config.json"), "r") as f:
    config = json.load(f)
discord_config = config["discord"]
admin_ids = {int(admin_id) for admin_id in discord_config["admin_ids"]}
channel_ids = {int(channel_id) for channel_id in discord_config["channel_ids"]}

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=discord_config["prefix"], intents=intents)

auto_trader = None

trade_queue = {}


@bot.event
async def on_ready():
    print(f"Connected to {len(bot.guilds)} servers")


@bot.command()
async def screencap(ctx, filename):
    if ctx.author.id not in admin_ids:
        return
    if auto_trader is None:
        await ctx.send("Trader not active")
        return

    auto_trader.screen_capture(filename)
    await ctx.message.reply("Done")


@bot.command()
async def restart(ctx):
    global t
    if ctx.author.id not in admin_ids:
        return
    t = threading.Thread(target=auto_trader.process_queue, daemon=True)
    t.start()
    await ctx.message.reply("Done")


@bot.command()
async def request(ctx, chip_name, chip_code):
    if ctx.channel.id in channel_ids:
        return

    if auto_trader is None:
        await ctx.send("Bot not running, cannot trade chips.")
        return

    if chip_code == "*":
        code = Code.Star
    else:
        code = Code[chip_code.upper()]

    chip = auto_trader.get_chip(chip_name, code)
    if chip is None:
        await ctx.message.reply(f'Invalid chip: "{chip_name} {chip_code}" not found.')
        return

    loop = asyncio.get_running_loop()

    def ready_cb(user: str, requested_chip: Chip, room_code_image: bytes):
        asyncio.ensure_future(
            ctx.author.send(
                f"{user}, your `{requested_chip.name}` is ready! You have 180 seconds to join",
                silent=False,
                file=discord.File(fp=io.BytesIO(room_code_image), filename="roomcode.png"),
            ),
            loop=loop,
        )

    def failure_cb(failure_reason: FailureReason, failure_message: str):
        if failure_reason in [FailureReason.AlreadyInQueue, FailureReason.InvalidInput, FailureReason.UserTimeOut]:
            asyncio.ensure_future(ctx.message.reply(failure_message), loop=loop)
        else:
            asyncio.ensure_future(
                ctx.message.reply(f"Unexpected failure `{failure_reason}`. <@174603401479323649>"), loop=loop
            )

    def added_cb(message: str):
        asyncio.ensure_future(ctx.message.add_reaction("✅"), loop=loop)
        asyncio.ensure_future(ctx.message.reply(message), loop=loop)

    auto_trader.add_to_queue(f"<@{ctx.author.id}>", chip, ready_cb, failure_cb, added_cb)


@bot.command()
async def clearqueue(ctx):
    if ctx.author.id not in admin_ids:
        return

    if auto_trader is None:
        await ctx.send("Bot not running.")
        return

    while not auto_trader.trading_queue.empty():
        try:
            auto_trader.trading_queue.get_nowait()
        except queue.Empty:
            break

    await ctx.send("Cleared the queue")


@bot.command()
async def cancel(ctx):
    if ctx.channel.id not in channel_ids:
        return

    if auto_trader is None:
        await ctx.send("Bot not running.")
        return
    auto_trader.remove_from_queue(f"<@{ctx.author.id}>")
    await ctx.message.reply("You have been removed from the queue.")


if __name__ == "__main__":
    capture = cv.VideoCapture(0)
    if not capture.isOpened():
        print("Error opening camera")
        sys.exit(1)

    with SocketSink("raspberrypi.local", 3000) as sink:
        controller = Controller(sink)

        auto_trader = AutoTrader(controller, capture)
        t = threading.Thread(target=auto_trader.process_queue, daemon=True)
        t.start()

        bot.run(discord_config["client_secret"])
