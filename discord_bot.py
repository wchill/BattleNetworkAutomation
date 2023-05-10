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
bot = commands.Bot(
    command_prefix=discord_config["prefix"],
    owner_ids=set(int(admin_id) for admin_id in discord_config["admin_ids"]),
    intents=intents,
)


@bot.event
async def on_ready():
    print(f"Connected to {len(bot.guilds)} servers")


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
