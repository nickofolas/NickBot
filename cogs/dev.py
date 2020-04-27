import shlex
import subprocess
import time
import io
from contextlib import redirect_stdout
import traceback
import textwrap
import asyncio
import os
import copy
from typing import Union
import datetime
import re

import discord
from discord.ext import commands
import aiosqlite as asq
from tabulate import tabulate
import import_expression
import humanize

from utils.checks import is_owner_or_administrator
from utils.paginator import ShellMenu, CSMenu
from utils.helpers import return_lang_hl
import utils


async def do_shell(args):
    shell = os.getenv("SHELL") or "/bin/bash"
    process = await asyncio.create_subprocess_shell(
        f'{shell} -c "{args}"',
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE)
    stdout, stderr = await process.communicate()
    return stdout, stderr


async def copy_ctx(
        self, ctx, command_string, *,
        channel: discord.TextChannel = None,
        author: Union[discord.Member, discord.User] = None):
    msg = copy.copy(ctx.message)
    msg.channel = channel or ctx.channel
    msg.author = author or ctx.author
    msg.content = ctx.prefix + command_string
    new_ctx = await self.bot.get_context(msg, cls=utils.context.Context)
    return new_ctx


def clean_bytes(line):
    """
    Cleans a byte sequence of shell directives and decodes it.
    """

    text = line.decode('utf-8').replace('\r', '').strip('\n')
    return re.sub(r'\x1b[^m]*m', '', text).replace("``", "`\u200b`").strip('\n')


def cleanup_code(self, content):
    """Automatically removes code blocks from the code."""
    # remove ```py\n```
    if content.startswith('```') and content.endswith('```'):
        return '\n'.join(content.split('\n')[1:-1])

    # remove `foo`
    return content.strip('` \n')


class Dev(commands.Cog):
    """Commands made to assist with bot development"""

    def __init__(self, bot):
        self.bot = bot
        self._last_result = None

    # Credit to Blank-Cheque for the basis for this
    @commands.command()
    @commands.is_owner()
    async def newcmd(self, ctx, *, code):
        """Create new commands using discord code blocks"""
        code = cleanup_code(self, code)
        exec(code)
        func = [
            v for k, v in locals().items() if k not in {'self', 'ctx', 'code'}
        ][0]  # Get the executed function from locals
        self.bot.add_command(func)
        func.cog = self
        await ctx.send(f'Successfully added new command {func.name}')

    @commands.command(aliases=['sh'])
    @commands.is_owner()
    async def shell(self, ctx, *, args):
        """Invokes the system shell,
        attempting to run the inputted command"""
        hl_lang = 'sh'
        if 'cat' in args:
            hl_lang = return_lang_hl(args)
        stdout, stderr = await do_shell(args)
        output = stdout + stderr
        entries = list(clean_bytes(output))
        source = ShellMenu(entries, code_lang=hl_lang, per_page=1985)
        menu = CSMenu(source, delete_message_after=True)
        await menu.start(ctx)

    @commands.command(name='eval')
    @commands.is_owner()
    async def eval_(self, ctx, *, body: str):
        """Runs code that you input to the command"""

        env = {
            'bot': self.bot,
            'ctx': ctx,
            'channel': ctx.channel,
            'author': ctx.author,
            'guild': ctx.guild,
            'message': ctx.message,
            '_': self._last_result
        }

        env.update(globals())

        body = cleanup_code(self, body)
        stdout = io.StringIO()

        to_compile = f'async def func():\n{textwrap.indent(body, "  ")}'

        try:
            import_expression.exec(to_compile, env)
        except Exception as e:
            return await ctx.safe_send(f'```py\n{e.__class__.__name__}: {e}\n```')

        func = env['func']
        try:
            with redirect_stdout(stdout):
                ret = await func()
        except Exception:
            value = stdout.getvalue()
            await ctx.safe_send(f'```py\n{value}{traceback.format_exc()}\n```')
        else:
            value = stdout.getvalue()
            try:
                await ctx.message.add_reaction(ctx.tick(True))
            except Exception:
                pass
            if ret is None:
                if value:
                    await ctx.safe_send(f'```py\n{value}\n```')
            else:
                self._last_result = ret
                await ctx.safe_send(f'```py\n{value}{ret}\n```')

    @commands.command()
    @commands.is_owner()
    async def debug(self, ctx, *, command_string):
        """Runs a command, checking for errors and returning exec time"""
        start = time.perf_counter()
        new_ctx = await copy_ctx(self, ctx, command_string)
        stdout = io.StringIO()
        try:
            with redirect_stdout(stdout):
                await new_ctx.reinvoke()
        except Exception:
            await ctx.message.add_reaction('❗')
            value = stdout.getvalue()
            paginator = commands.Paginator(prefix='```py')
            for line in (value + traceback.format_exc()).split('\n'):
                paginator.add_line(line)
            for page in paginator.pages:
                await ctx.author.send(page)
            return
        end = time.perf_counter()
        await ctx.send(f'Cmd `{command_string}` executed in {end-start:.3f}s')

    @commands.command()
    @commands.is_owner()
    async def clean(self, ctx, amount: int = 10):
        """Cleanup messages from the bot"""
        try:
            await ctx.message.delete()
        except Exception:
            pass
        async for m in ctx.channel.history(limit=amount):
            if m.author == self.bot.user:
                await m.delete()

    @commands.command()
    @is_owner_or_administrator()
    async def prefix(self, ctx, new_prefix):
        """Change the prefix for the current server"""
        async with asq.connect('./database.db') as db:
            try:
                await db.execute("UPDATE guild_prefs SET prefix=$1 WHERE guild_id=$2", (new_prefix, ctx.guild.id))
                await db.commit()
            except Exception:
                await db.execute("INSERT INTO guild_prefs (guild_id, prefix) VALUES ($1, $2)", (ctx.guild.id, new_prefix))
                await db.commit()

        await ctx.guild.get_member(
            self.bot.user.id).edit(nick=f'Nick of O-Bot [{new_prefix}]')
        await ctx.send(f'Prefix successfully changed to `{new_prefix}`')

    @commands.command()
    @commands.is_owner()
    async def sql(self, ctx, *, query: str):
        async with asq.connect('./database.db') as db:
            out = await db.execute(query)
            res = await out.fetchall()
            try:
                names = list(map(lambda x: x[0], out.description))
                table = tabulate(list(res), headers=names, tablefmt='pretty')
                await ctx.safe_send(f"```\n{table}```")
            except Exception:
                await db.commit()
                await ctx.safe_send(f"Executed ```sql\n{query}```")

    @commands.group(name='dev')
    @commands.is_owner()
    async def dev_command_group(self, ctx):
        pass

    @dev_command_group.command(name='logs')
    @commands.is_owner()
    async def view_journal_ctl(self, ctx):
        stdout, stderr = await do_shell('journalctl -u mybot -n 300 --no-pager -q')
        output = stdout + stderr
        entries = list(clean_bytes(output))
        source = ShellMenu(entries, code_lang='sh', per_page=1985)
        menu = CSMenu(source, delete_message_after=True)
        await menu.start(ctx)

    @commands.group(name='edit')
    @commands.is_owner()
    async def edit_bot(self, ctx):
        """Edit various parts of the bot's user"""
        pass

    @edit_bot.command()
    @commands.is_owner()
    async def nick(self, ctx, *, new_nickname=None):
        """
        Change the bot's nickname in the current guild
        Pass nothing to reset nickname
        """
        await ctx.me.edit(nick=new_nickname)
        await ctx.message.add_reaction(ctx.tick(True))

    @edit_bot.command()
    @commands.is_owner()
    async def presence(self, ctx, act_type, *, message=None):
        """Edit the bot's presence
        Available activity types:
            - playing
            - streaming
            - listening
            - watching
            - none (this will reset the status and reenable tasks loop)
        """
        type_dict = {
            'playing': 0,
            'streaming': 1,
            'listening': 2,
            'watching': 3,
            'none': 4
        }
        async with ctx.ExHandler(
                exception_type=KeyError,
                propagate=(self.bot, ctx),
                message='Not a valid activity type') as man:
            if type_dict[act_type] == 4:
                self.bot.persistent_status = False
            else:
                self.bot.persistent_status = True
            await self.bot.change_presence(
                activity=discord.Activity(
                    type=type_dict[act_type], name=message))
            await ctx.message.add_reaction(ctx.tick(True))

    @commands.group(invoke_without_command=True)
    @commands.is_owner()
    async def sudo(self, ctx, target: Union[discord.Member, discord.User], *, command):
        """Run command as another user"""
        new_ctx = await copy_ctx(self, ctx, command, author=target)
        await self.bot.invoke(new_ctx)

    @sudo.command(name='in')
    @commands.is_owner()
    async def _in(
            self, ctx,
            channel: discord.TextChannel,
            *, command):
        new_ctx = await copy_ctx(
            self, ctx, command, channel=channel)
        await self.bot.invoke(new_ctx)

    @commands.command()
    @commands.is_owner()
    async def reboot(self, ctx):
        """Kills all of the bot's processes"""
        response = await ctx.prompt('Are you sure you want to reboot?')
        if response:
            await self.bot.close()

    @commands.command()
    @commands.is_owner()
    async def load(self, ctx, *, extension):  # Cog loading
        extension = extension.split(' ')
        ls = []
        if len(extension) == 1 and extension[0] in ('*', 'all', 'a'):
            await ctx.message.add_reaction('<a:loading:681628799376293912>')
            for filename in os.listdir('./cogs'):
                try:
                    if not filename.endswith('.py') or filename == 'dev.py':
                        continue
                    self.bot.load_extension(f'cogs.{filename[:-3]}')
                except Exception:
                    continue
            await ctx.message.remove_reaction('<a:loading:681628799376293912>', ctx.me)
            await ctx.message.add_reaction(ctx.tick(True))
        else:
            for e in extension:
                self.bot.load_extension(f'cogs.{e.lower()}')
                ls.append(e)
            await ctx.message.add_reaction(ctx.tick(True))

    @commands.command()
    @commands.is_owner()
    async def unload(self, ctx, *, extension):  # Cog loading
        extension = extension.split(' ')
        ls = []
        if len(extension) == 1 and extension[0] in ('*', 'all', 'a'):
            await ctx.message.add_reaction('<a:loading:681628799376293912>')
            for filename in os.listdir('./cogs'):
                try:
                    if not filename.endswith('.py') or filename == 'dev.py':
                        continue
                    self.bot.unload_extension(f'cogs.{filename[:-3]}')
                except Exception:
                    continue
            await ctx.message.remove_reaction('<a:loading:681628799376293912>', ctx.me)
            await ctx.message.add_reaction(ctx.tick(True))
        else:
            if 'dev' in [ex.lower() for ex in extension]:
                return await ctx.send('The "dev" cog cannot be unloaded')
            for e in extension:
                self.bot.unload_extension(f'cogs.{e.lower()}')
                ls.append(e)
            await ctx.message.add_reaction(ctx.tick(True))

    @commands.command()
    @commands.is_owner()
    async def reload(self, ctx, *, extension):  # Cog loading
        extension = extension.split(' ')
        """Pulls from git and then reloads all or specified cogs"""
        await ctx.message.add_reaction('<a:loading:681628799376293912>')
        await do_shell('git pull')
        errored = []
        if len(extension) == 1 and extension[0] in ('*', 'all', 'a'):
            for filename in os.listdir('./cogs'):
                try:
                    if not filename.endswith('.py'):
                        continue
                    self.bot.reload_extension(f'cogs.{filename[:-3]}')
                except Exception:
                    errored.append(filename[:-3])
            await ctx.message.remove_reaction('<a:loading:681628799376293912>', ctx.me)
            if errored:
                await ctx.send('\nThe following cogs errored while reloading: ' + ', '.join(errored))
            else:
                await ctx.message.add_reaction(ctx.tick(True))
        else:
            for e in extension:
                self.bot.reload_extension(f'cogs.{e.lower()}')
                errored.append(e)
            await ctx.send(f'Succesfully reloaded cog(s) {", ".join(errored)}')
            await ctx.message.remove_reaction('<a:loading:681628799376293912>', ctx.me)

    '''
    @commands.command(name='socketstats')
    async def view_socket_stats(self, ctx):
        """View the websocket status for the bot"""
        stats, out = (self.bot.socket_stats, [])
        delta = datetime.datetime.utcnow() - self.bot.launch_time
        mins = round(delta.total_seconds() / 60)
        total_events = sum(stats.values())
        per_min = round(total_events / mins)
        for en in sorted(stats, key=stats.get, reverse=True):
            if en is None:
                continue
            out.append(f'{en:<30}' + f' │ {stats[en]:,}')
        await ctx.safe_send(
            embed=discord.Embed(
                title=f'{total_events:,} socket events in '
                f'{humanize.naturaldelta(delta)}\n'
                f'*{per_min:,} events per minute*\n',
                description='```' + '\n'.join(out) + '```',
                color=discord.Color.main))
    '''


def setup(bot):
    bot.add_cog(Dev(bot))
