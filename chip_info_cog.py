import json
import os

from discord.ext import commands

from chip import Chip, Code
from chip_list import ChipList

with open(os.path.join(os.path.dirname(__file__), "config.json"), "r") as f:
    config = json.load(f)
discord_config = config["discord"]

CHANNEL_IDS = {int(channel_id) for channel_id in discord_config["info_channel_ids"]}


class ChipInfoCog(commands.Cog, name="Chip Info"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command()
    async def chipcode(self, ctx: commands.Context, chip_code: str):
        if chip_code == "*":
            actual_chip_code = Code.Star
        else:
            actual_chip_code = Code[chip_code.upper()]

        text = []
        for chip in ChipList.ALL_CHIPS:
            if chip.code == actual_chip_code:
                text.append(chip.name)
        await ctx.message.reply(", ".join(text))

    """
    @commands.command()
    async def chip(self, ctx: commands.Context, chip_name: str):
        if chip_code == "*":
            actual_chip_code = Code.Star
        else:
            actual_chip_code = Code[chip_code.upper()]

        lines = ["```"]
        for chip in ChipList.ALL_CHIPS:
            if chip.code == actual_chip_code:
                lines.append(str(chip))
        lines.append("```")
        await ctx.message.reply("\n".join(lines))
    """
