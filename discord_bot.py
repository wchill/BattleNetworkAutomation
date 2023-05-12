from __future__ import annotations

import asyncio
import json
import os

import discord
from discord.ext import commands

import utils
from utils import MessageReaction

COGS = ["info_cog", "admin_cog", "trade_cog"]


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


@bot.command()
@commands.is_owner()
async def reloadcog(ctx: commands.Context, cog_name: str):
    try:
        await bot.reload_extension(cog_name)
        await ctx.message.add_reaction(MessageReaction.OK.value)
    except Exception as e:
        await ctx.message.add_reaction(MessageReaction.ERROR.value)
        await ctx.message.reply(f"Error when reloading {cog_name}: {e}")


@bot.command()
@commands.is_owner()
async def reloadall(ctx: commands.Context):
    for cog in COGS:
        try:
            await bot.reload_extension(cog)
        except Exception as e:
            await ctx.message.add_reaction(MessageReaction.ERROR.value)
            await ctx.message.reply(f"Error when reloading {cog}: {e}")
            return
    await ctx.message.add_reaction(MessageReaction.OK.value)
    cogs_list = '", "'.join(COGS)
    await ctx.message.reply(f'Successfully reloaded {len(COGS)} cogs: "{cogs_list}"')


async def main():
    utils.wait_port("discord.com", 443)
    for ext in COGS:
        await bot.load_extension(ext)
    await bot.start(discord_config["client_secret"])


if __name__ == "__main__":
    asyncio.run(main())
