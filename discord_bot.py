from __future__ import annotations

import asyncio
import json
import multiprocessing
import os

import discord
from discord.ext import commands

from info_cog import InfoCog
from trade_cog import TradeCog
from trade_manager import TradeManager

with open(os.path.join(os.path.dirname(__file__), "config.json"), "r") as f:
    config = json.load(f)
discord_config = config["discord"]

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=discord_config["prefix"], owner_id=174603401479323649, intents=intents)


@bot.event
async def on_ready():
    print(f"Connected to {len(bot.guilds)} servers")


"""
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
async def reset(ctx):
    if ctx.author.id not in admin_ids:
        return
    if auto_trader is None:
        await ctx.send("Trader not active")
        return

    auto_trader.reset()
    await ctx.message.reply("Done")

@bot.command()
async def restart(ctx):
    global t
    if ctx.author.id not in admin_ids:
        return
    t = threading.Thread(target=auto_trader.process_queue, daemon=True)
    t.start()
    await ctx.message.reply("Done")
"""


def main():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    request_queue = multiprocessing.Queue()
    image_send_queue = multiprocessing.JoinableQueue()
    message_queue = multiprocessing.SimpleQueue()

    trade_manager = TradeManager(request_queue, image_send_queue, message_queue)
    trade_manager.start_processing()

    loop.run_until_complete(bot.add_cog(TradeCog(bot, trade_manager)))
    loop.run_until_complete(bot.add_cog(InfoCog(bot)))
    bot.run(discord_config["client_secret"])


if __name__ == "__main__":
    main()
