"""
neo Discord bot
Copyright (C) 2021 nickofolas

neo is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published
by the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

neo is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with neo.  If not, see <https://www.gnu.org/licenses/>.
"""
import ast
import asyncio
import copy
import inspect
import io
import os
import re
import textwrap
import time
import traceback
from collections import namedtuple
from contextlib import redirect_stdout, suppress
from typing import Union

import asyncpg
import discord
import import_expression
import neo
from discord.ext import commands, flags
from neo.utils.converters import BoolConverter, CBStripConverter
from neo.utils.eval_backend import (NeoEval, clear_intersection,
                                    format_exception)
from neo.utils.formatters import clean_bytes, group, pluralize
from tabulate import tabulate

status_dict = {
    "online": discord.Status.online,
    "offline": discord.Status.offline,
    "dnd": discord.Status.dnd,
    "idle": discord.Status.idle,
}
type_dict = {
    "playing": 0,
    "streaming": "streaming",
    "listening": 2,
    "watching": 3,
    "none": None,
}

file_ext_re = re.compile(r"(\~?\/?(\w/)*)?\.(?P<extension>\w*)$")

ShellOut = namedtuple("ShellOut", "stdout stderr returncode")


async def do_shell(cmd):
    process = await asyncio.create_subprocess_shell(
        cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await process.communicate()
    return ShellOut(stdout, stderr, str(process.returncode))


async def copy_ctx(
    ctx,
    command_string,
    *,
    channel: discord.TextChannel = None,
    author: Union[discord.Member, discord.User] = None,
):
    msg = copy.copy(ctx.message)
    msg.channel = channel or ctx.channel
    msg.author = author or ctx.author
    msg.content = ctx.prefix + command_string
    new_ctx = await ctx.bot.get_context(msg)
    return new_ctx


class Dev(commands.Cog):
    """Commands made to assist with bot development"""

    def __init__(self, bot):
        self.bot = bot
        self.scope = {}
        self._last_result = None

    async def cog_check(self, ctx):
        return await self.bot.is_owner(ctx.author)

    @commands.command(aliases=["sh"])
    async def shell(self, ctx, *, args: CBStripConverter):
        """Invokes the system shell, attempting to run the inputted command"""
        hl_lang = "sh"
        if match := file_ext_re.search(args):
            hl_lang = match.groupdict().get("extension", "sh")
        if "git diff" in args:
            hl_lang = "diff"
        async with ctx.loading(tick=False):
            shellout = await do_shell(args)
            output = (
                clean_bytes(shellout.stdout)
                + "\n"
                + textwrap.indent(clean_bytes(shellout.stderr), "[stderr] ")
            )
            pages = group(output, 1500)
            pages = [
                str(ctx.codeblock(content=page, lang=hl_lang))
                + f"\n`Return code {shellout.returncode}`"
                for page in pages
            ]
        await ctx.paginate(
            pages, 1, delete_on_button=True, clear_reactions_after=True, timeout=1800
        )

    @commands.command(name="eval", aliases=["e"])
    async def eval_(self, ctx, *, body: CBStripConverter):
        """Runs code that you input to the command"""
        env = {
            "bot": self.bot,
            "ctx": ctx,
            "channel": ctx.channel,
            "author": ctx.author,
            "guild": ctx.guild,
            "message": ctx.message,
            "_": self._last_result,
        }
        clear_intersection(globals(), self.scope)
        env.update(**globals(), **self.scope)
        stdout = io.StringIO()
        to_return = None
        final_results = []
        async with ctx.loading():
            try:
                async for res in NeoEval(code=body, context=env, scope=self.scope):
                    if res is None:
                        continue
                    self._last_result = res
                    if not isinstance(res, str):
                        res = repr(res)
                    final_results.append(res)
            except Exception as e:
                to_return = format_exception(e)
            else:
                value = stdout.getvalue() or ""
                to_return = value + "\n".join(final_results)
        if to_return:
            pages = group(to_return, 1500)
            pages = [str(ctx.codeblock(content=page, lang="py")) for page in pages]
            await ctx.paginate(
                pages,
                1,
                delete_on_button=True,
                clear_reactions_after=True,
                timeout=1800,
            )

    @commands.command()
    async def debug(self, ctx, *, command_string):
        """Runs a command, checking for errors and returning exec time"""
        start = time.perf_counter()
        new_ctx = await copy_ctx(ctx, command_string)
        stdout = io.StringIO()
        try:
            with redirect_stdout(stdout):
                await new_ctx.reinvoke()
        except Exception:
            await ctx.message.add_reaction("❗")
            value = stdout.getvalue()
            paginator = commands.Paginator(prefix="```py")
            for line in (value + traceback.format_exc()).split("\n"):
                paginator.add_line(line)
            for page in paginator.pages:
                await ctx.author.send(page)
            return
        end = time.perf_counter()
        await ctx.send(f"Cmd `{command_string}` executed in {end - start:.3f}s")

    @commands.command()
    async def sql(self, ctx, *, query: CBStripConverter):
        """Run SQL statements"""
        is_multistatement = query.count(";") > 1
        if is_multistatement:
            strategy = self.bot.pool.execute
        else:
            strategy = self.bot.pool.fetch

        start = time.perf_counter()
        try:
            results = await strategy(query)
        except asyncpg.PostgresError as error:
            await ctx.send(
                ctx.codeblock(
                    content=tabulate([[str(error)]], headers=["error"]), lang="sql"
                )
            )
            return

        dt = (time.perf_counter() - start) * 1000.0

        rows = len(results)
        if is_multistatement or rows == 0:
            return await ctx.send(f"`{dt:.2f}ms: {results}`")
        rkeys = [*results[0].keys()]
        headers = [
            textwrap.shorten(col, width=40 // len(rkeys), placeholder="")
            for col in rkeys
        ]
        r = []
        for item in [list(res.values()) for res in results]:
            for i in item:
                r.append(
                    textwrap.shorten(str(i), width=40 // len(rkeys), placeholder="")
                )
        r = group(r, len(rkeys))
        table = tabulate(r, headers=headers, tablefmt="pretty")
        pages = [str(ctx.codeblock(content=page)) for page in group(table, 1500)]
        await ctx.paginate(
            pages,
            1,
            delete_on_button=True,
            clear_reactions_after=True,
            timeout=300,
            template=discord.Embed().set_author(
                name=f'Returned {rows} {pluralize("row", rows)} in {dt:.2f}ms'
            ),
        )

    @commands.group(name="dev", invoke_without_command=True)
    async def dev_command_group(self, ctx):
        """Some dev commands"""

    @dev_command_group.command(name="delete", aliases=["del"])
    async def delete_bot_msg(self, ctx, message_ids: commands.Greedy[int]):
        for m_id in message_ids:
            converter = commands.MessageConverter()
            m = await converter.convert(ctx, str(m_id))
            if not m.author.bot:
                raise commands.CommandError("I can only delete my own messages")
            await m.delete()
        await ctx.message.add_reaction(ctx.tick(True))

    @dev_command_group.command(name="clean")
    async def _bulk_clean(self, ctx, amount: int = 5):
        async with ctx.loading():
            await ctx.channel.purge(
                limit=amount, bulk=False, check=lambda m: m.author == ctx.me
            )

    @dev_command_group.command(name="source", aliases=["src"])
    async def _dev_src(self, ctx, *, obj):
        new_ctx = await copy_ctx(ctx, f"eval return inspect!.getsource({obj})")
        await new_ctx.reinvoke()

    @dev_command_group.command(name="journalctl", aliases=["jctl"])
    async def _dev_journalctl(self, ctx):
        new_ctx = await copy_ctx(ctx, f"sh sudo journalctl -u neo -o cat")
        await new_ctx.reinvoke()

    @flags.add_flag(
        "-s", "--status", default="online", choices=["online", "offline", "dnd", "idle"]
    )
    @flags.add_flag("-p", "--presence", nargs="+", dest="presence")
    @flags.add_flag("-n", "--nick", nargs="?", const="None")
    @flags.command(name="edit")
    async def args_edit(self, ctx, **flags):
        """Edit the bot"""
        if pres := flags.get("presence"):
            if type_dict.get(pres[0]) is None:
                await self.bot.change_presence(status=ctx.me.status)
            elif type_dict.get(pres[0]) == "streaming":
                pres.pop(0)
                await self.bot.change_presence(
                    activity=discord.Streaming(
                        name=" ".join(pres), url="https://www.twitch.tv/#"
                    )
                )
            else:
                await self.bot.change_presence(
                    status=ctx.me.status,
                    activity=discord.Activity(
                        type=type_dict[pres.pop(0)], name=" ".join(pres)
                    ),
                )
        if nick := flags.get("nick"):
            await ctx.me.edit(nick=nick if nick != "None" else None)
        if stat := flags.get("status"):
            await self.bot.change_presence(
                status=status_dict[stat.lower()], activity=ctx.me.activity
            )
        await ctx.message.add_reaction(ctx.tick(True))

    @commands.group(invoke_without_command=True)
    async def sudo(
        self, ctx, target: Union[discord.Member, discord.User, None], *, command
    ):
        """Run command as another user, or with all checks bypassed"""
        if not isinstance(target, (discord.Member, discord.User)):
            new_ctx = await copy_ctx(ctx, command, author=ctx.author)
            await new_ctx.reinvoke()
            return
        new_ctx = await copy_ctx(ctx, command, author=target)
        await self.bot.invoke(new_ctx)

    @commands.command(aliases=["die", "kys"])
    async def reboot(self, ctx):
        """Kills the bot"""
        if (response := await ctx.prompt("Are you sure you want to reboot?")) :
            await self.bot.close()

    @commands.command(name="screenshot", aliases=["ss"])
    async def _website_screenshot(self, ctx, *, site):
        """Take a screenshot of a site"""
        async with ctx.loading(tick=False):
            response = await self.bot.session.get(
                "https://magmafuck.herokuapp.com/api/v1", headers={"website": site}
            )
            data = await response.json()
            site = data["website"]
            await ctx.send(
                embed=discord.Embed(title=site, url=site).set_image(
                    url=data["snapshot"]
                )
            )

    @flags.add_flag("-m", "--mode", choices=["r", "l", "u"], default="r")
    @flags.add_flag("-p", "--pull", action="store_true")
    @flags.add_flag("extension", nargs="*")
    @flags.command(name="extensions", aliases=["ext"])
    async def _dev_extensions(self, ctx, **flags):
        """Manage extensions"""
        async with ctx.loading():
            mode_mapping = {
                "r": self.bot.reload_extension,
                "l": self.bot.load_extension,
                "u": self.bot.unload_extension,
            }
            if flags.get("pull"):
                await do_shell("git pull")
            mode = mode_mapping.get(flags["mode"])
            extensions = (
                neo.conf["exts"] if flags["extension"][0] == "~" else flags["extension"]
            )
            for ext in extensions:
                mode(ext)

    @commands.command(name="blacklist", aliases=["bl"])
    async def _toggle_blacklist(
        self, ctx, target: Union[discord.Member, discord.User, int]
    ):
        target = target.id if not isinstance(target, int) else target
        if target in self.bot.owner_ids:
            raise commands.CommandError("What the fuck no you don't get to do that")

        async with ctx.loading():
            if not (_u := self.bot.user_cache.get(target)):
                with suppress(Exception):
                    await self.bot.pool.execute(
                        "INSERT INTO user_data (user_id) VALUES ($1)", target
                    )
                _blacklisted = False
            else:
                _blacklisted = _u["_blacklisted"]
            await self.bot.pool.execute(
                "UPDATE user_data SET _blacklisted=$1 WHERE user_id=$2",
                not _blacklisted,
                target,
            )
            await self.bot.user_cache.refresh()


def setup(bot):
    bot.add_cog(Dev(bot))
