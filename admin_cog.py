import asyncio
import datetime
import json
import math
import os
import platform
import socket
import sys

import cpuinfo
import discord
import psutil
from discord.ext import commands

import utils
from utils import MessageReaction

RESTART_FILE = os.path.expanduser("~/.bot_restarted")


class AdminCog(commands.Cog, name="Admin"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        if os.path.exists(RESTART_FILE):
            with open(RESTART_FILE, "r") as f:
                message_info = json.load(f)
            discord_channel = self.bot.get_channel(message_info["channel_id"])
            discord_message = await discord_channel.fetch_message(message_info["message_id"])
            await discord_message.reply("Successfully restarted!")
            os.unlink(RESTART_FILE)
        print("Admin cog successfully loaded")

    @commands.command()
    @commands.is_owner()
    async def restartbot(self, ctx: commands.Context):
        await ctx.message.add_reaction(MessageReaction.OK.value)
        await ctx.message.reply("Restarting the bot now!")
        with open(RESTART_FILE, "w") as f:
            json.dump({"channel_id": ctx.channel.id, "message_id": ctx.message.id}, f)

        os.system("systemctl restart discord-bot")

    @commands.command()
    @commands.is_owner()
    async def restartsystem(self, ctx: commands.Context):
        await ctx.message.add_reaction(MessageReaction.OK.value)
        await ctx.message.reply("Restarting the bot machine now!")
        with open(RESTART_FILE, "w") as f:
            json.dump({"channel_id": ctx.channel.id, "message_id": ctx.message.id}, f)

        os.system("reboot")

    @commands.command()
    @commands.is_owner()
    async def update(self, ctx: commands.Context):
        await ctx.message.add_reaction(MessageReaction.OK.value)
        await ctx.message.reply("Updating the bot from GitHub")
        await utils.run_shell("git fetch --all && git reset --hard origin/master", cwd=os.path.dirname(__file__))

    async def run_cpuinfo(self):
        def _utf_to_str(utf):
            if isinstance(utf, list):
                return [_utf_to_str(element) for element in utf]
            elif isinstance(utf, dict):
                return {_utf_to_str(key): _utf_to_str(value) for key, value in utf.items()}
            else:
                return utf

        async def get_cpu_info_json():
            p1 = await asyncio.create_subprocess_exec(
                sys.executable, cpuinfo.cpuinfo.__file__, "--json", stdout=asyncio.subprocess.PIPE
            )
            stdout, _ = await p1.communicate()

            if p1.returncode != 0:
                return "{}"

            return stdout.decode(encoding="UTF-8")

        data = await get_cpu_info_json()
        return json.loads(data, object_hook=_utf_to_str)

    @commands.command()
    async def status(self, ctx: commands.Context):
        try:
            load1, load5, load15 = psutil.getloadavg()
            virt_mem = psutil.virtual_memory()
            disk_usage = psutil.disk_usage(os.path.abspath("."))

            creation_time = psutil.Process(os.getpid()).create_time()
            boot_time = psutil.boot_time()
            unix_timestamp = (datetime.datetime.now() - datetime.datetime(1970, 1, 1)).total_seconds()
            uptime = math.floor(unix_timestamp - creation_time)
            system_uptime = math.floor(unix_timestamp - boot_time)

            cpu_info = await self.run_cpuinfo()
            soc = cpu_info.get("hardware_raw")
            cpu_name = cpu_info.get("brand_raw")
            display_cpu_name = f"{soc} ({cpu_name})" if soc else cpu_name
            architecture = platform.uname().machine
            python_ver = cpu_info.get("python_version")
            clock_speed = cpu_info.get("hz_actual_friendly")

            core_count = psutil.cpu_count(False)
            thread_count = psutil.cpu_count()

            if platform.system() == "Windows":
                output = await utils.run_shell(
                    'powershell.exe -c "Get-CimInstance Win32_OperatingSystem | Select Caption, Version | ConvertTo-Json"'
                )
                data = json.loads(output)
                os_name = data["Caption"]
                os_build = data["Version"]
            else:
                uname = platform.uname()
                os_name = f"{uname.system} {uname.release}"
                os_build = uname.version

            git_version = (await utils.run_shell("git describe --always", cwd=os.path.dirname(__file__))).strip()

            embed = discord.Embed(title="Bot status")
            embed.add_field(name="Hostname", value=socket.gethostname())
            embed.add_field(name="OS", value=f"{os_name}")
            embed.add_field(name="OS build", value=os_build)
            embed.add_field(
                name="CPU",
                value=f"{display_cpu_name} ({architecture}, {clock_speed}, {core_count} cores, {thread_count} threads)",
            )
            embed.add_field(name="CPU usage", value=f"Load average (1/5/15 min):\n{load1}, {load5}, {load15}")
            embed.add_field(
                name="Memory usage", value=f"{virt_mem[3]/(1024 ** 2):.2f}/{virt_mem[0]/(1024 ** 2):.2f} MB"
            )
            embed.add_field(
                name="Disk usage", value=f"{disk_usage.used/(1024 ** 3):.2f}/{disk_usage.total/(1024 ** 3):.2f} GB"
            )
            embed.add_field(name="Python version", value=python_ver)
            embed.add_field(name="Discord.py version", value=discord.__version__)
            embed.add_field(name="Bot version (git)", value=git_version)
            embed.add_field(name="Bot uptime", value=str(datetime.timedelta(seconds=uptime)))
            embed.add_field(name="System uptime", value=str(datetime.timedelta(seconds=system_uptime)))

            await ctx.message.reply(embed=embed)
        except Exception:
            import traceback

            traceback.print_exc()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AdminCog(bot))
