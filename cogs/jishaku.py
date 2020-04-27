from discord.ext import commands
from jishaku.cog import JishakuBase
from jishaku.metacog import GroupCogMeta
from jishaku.flags import JISHAKU_HIDE
from jishaku.meta import __version__
import discord
import humanize
import sys
from jishaku.modules import package_version
from jishaku.codeblocks import Codeblock, codeblock_converter
import psutil

@commands.group(name="jishaku", aliases=["jsk"], hidden=JISHAKU_HIDE,
                invoke_without_command=True, ignore_extra=False)
async def jsk(self, ctx):
    summary = [
        f"Jishaku v{__version__}, discord.py `{package_version('discord.py')}`, "
        f"`Python {sys.version}` on `{sys.platform}`".replace("\n", "")
    ]

    if sys.version_info < (3, 7, 0):
        summary.extend([
            "Jishaku no longer has primary support for Python 3.6. While the cog will still work, some "
            "features and bugfixes may be unavailable on this version.",
            "It is recommended that you update to Python 3.7+ when possible so Jishaku can properly "
            "leverage new language features.",
            ""
        ])

    if psutil:
        try:
            proc = psutil.Process()

            with proc.oneshot():
                try:
                    mem = proc.memory_full_info()
                    summary.append(f"Using {humanize.naturalsize(mem.rss)} physical memory and "
                                   f"{humanize.naturalsize(mem.vms)} virtual memory, "
                                   f"{humanize.naturalsize(mem.uss)} of which unique to this process.")
                except psutil.AccessDenied:
                    pass

                try:
                    name = proc.name()
                    pid = proc.pid
                    thread_count = proc.num_threads()

                    summary.append(f"Running on PID {pid} (`{name}`) with {thread_count} thread(s).")
                except psutil.AccessDenied:
                    pass

        except psutil.AccessDenied:
            summary.append(
                "psutil is installed, but this process does not have high enough access rights "
                "to query process information."
            )

    cache_summary = f"{len(self.bot.guilds)} guild(s) and {len(self.bot.users)} user(s)"

    if isinstance(self.bot, discord.AutoShardedClient):
        summary.append(f"This bot is automatically sharded and can see {cache_summary}.")
    elif self.bot.shard_count:
        summary.append(f"This bot is manually sharded and can see {cache_summary}.")
    else:
        summary.append(f"This bot is not sharded and can see {cache_summary}.")

    summary.append(f"Average websocket latency: {round(self.bot.latency * 1000, 2)}ms")
    embed = discord.Embed(color=self.bot.color)
    for group in summary:
        embed.add_field(name='_ _', value=group)
    await ctx.send(embed=embed)


class Jishaku(JishakuBase, metaclass=GroupCogMeta, command_parent=jsk):
    """
    A subclass of Jishaku that lets me customize behavior to my liking
    """
    @commands.command(name='pip3', aliases=['pip'])
    async def jsk_pip(self, ctx: commands.Context, *, argument: codeblock_converter):
        """
        Shortcut for 'jsk sh pip3'. Invokes the system shell.
        """

        return await ctx.invoke(self.jsk_shell, argument=Codeblock(argument.language, "pip3 " + argument.content))


def setup(bot):
    bot.add_cog(Jishaku(bot))
