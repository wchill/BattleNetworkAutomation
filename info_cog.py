import io
import json
import os

import discord
from discord.ext import commands

from chip import Chip, Code
from chip_list import ChipList
from navicust_part import Color
from navicust_part_list import NaviCustPartList

with open(os.path.join(os.path.dirname(__file__), "config.json"), "r") as f:
    config = json.load(f)
discord_config = config["discord"]

CHANNEL_IDS = {int(channel_id) for channel_id in discord_config["info_channel_ids"]}


class InfoCog(commands.Cog, name="Info"):
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

    @commands.command()
    async def chip(self, ctx: commands.Context, chip_name: str):
        chips = ChipList.get_chips_by_name(chip_name)
        if len(chips) == 0:
            await ctx.message.reply("That chip doesn't exist.")
            return

        # TODO: Get chip artwork
        chip = chips[0]
        image = discord.File(chip.chip_image_path, filename="chip.png")
        embed = discord.Embed(title=chip.name)
        embed.set_image(url="attachment://chip.png")
        embed.add_field(name="Description", value=chip.description, inline=False)
        embed.add_field(name="ID", value=chip.chip_id)
        embed.add_field(name="Codes", value=", ".join(c.code.name if c.code != Code.Star else "*" for c in chips))
        embed.add_field(
            name="Type", value={Chip.STANDARD: "Standard", Chip.MEGA: "Mega", Chip.GIGA: "Giga"}[chip.chip_type]
        )
        embed.add_field(name="Attack", value=chip.atk if chip.atk > 1 else "???" if chip.atk == 1 else "---")
        embed.add_field(name="Element", value=chip.element.name)
        embed.add_field(name="MB", value=f"{chip.mb} MB")

        await ctx.message.reply(embed=embed, file=image)

    @commands.command()
    async def ncp(self, ctx: commands.Context, part_name: str):
        parts = NaviCustPartList.get_parts_by_name(part_name)
        if len(parts) == 0:
            await ctx.message.reply("That part doesn't exist.")
            return

        # TODO: Get chip artwork
        part = parts[0]
        with io.BytesIO() as img:
            img.write(part.block_image)
            img.seek(0)
            image = discord.File(img, filename="ncp.png")
        embed = discord.Embed(title=part.name)
        embed.set_image(url="attachment://ncp.png")
        embed.add_field(name="Description", value=part.description, inline=False)
        embed.add_field(name="Colors", value=" ".join(p.color.value for p in parts))
        embed.add_field(name="Compression code", value=part.compression_code if part.compression_code else "None")
        embed.add_field(name="Bug", value=part.bug.name)

        await ctx.message.reply(embed=embed, file=image)

    @commands.command()
    async def ncpcolor(self, ctx: commands.Context, color: str):
        actual_color = Color[color.lower().capitalize()]

        text = []
        for part in NaviCustPartList.ALL_PARTS:
            if part.color == actual_color:
                text.append(part.name)
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
