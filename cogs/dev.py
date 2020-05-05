import time
import io
from contextlib import redirect_stdout
import traceback
import textwrap
import asyncio
import os
import copy
from typing import Union
import re
import argparse
import shlex

import discord
from discord.ext import commands
import aiosqlite as asq
from tabulate import tabulate
import import_expression

from utils.checks import is_owner_or_administrator
from utils.paginator import ShellMenu, CSMenu
from utils.helpers import return_lang_hl, pluralize
import utils
from utils.config import conf


class Arguments(argparse.ArgumentParser):
    def error(self, message):
        raise RuntimeError(message)


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
        if 'git diff' in args:
            hl_lang = 'diff'
        await ctx.trigger_typing()
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
        sent = None

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
            sent = await ctx.safe_send(f'```py\n{value}{traceback.format_exc()}\n```')
        else:
            value = stdout.getvalue()
            try:
                await ctx.message.add_reaction(ctx.tick(True))
            except Exception:
                pass
            if ret is None:
                if value:
                    sent = await ctx.safe_send(f'{value}')
            else:
                self._last_result = ret
                if isinstance(ret, discord.Embed):
                    sent = await ctx.send(embed=ret)
                elif isinstance(ret, discord.File):
                    sent = await ctx.send(file=ret)
                else:
                    sent = await ctx.safe_send(f'{value}{ret}')
        if sent:
            await sent.add_reaction(ctx.tick(False))
            try:
                reaction, user = await self.bot.wait_for(
                    'reaction_add',
                    check=lambda r, u: r.message.id == sent.id and u.id == ctx.author.id,
                    timeout=30)
            except asyncio.TimeoutError:
                await sent.remove_reaction(ctx.tick(False), ctx.me)
            else:
                if str(reaction.emoji) == str(ctx.tick(False)):
                    await reaction.message.delete()

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
        await ctx.send(f'Cmd `{command_string}` executed in {end - start:.3f}s')

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
    async def prefix(self, ctx, new_prefix=None):
        """Change the prefix for the current server"""
        if new_prefix is None:
            return await ctx.send(embed=discord.Embed(
                title='Prefixes for this guild',
                description='\n'.join(
                    sorted(set([p.replace('@!', '@') for p in await self.bot.get_prefix(ctx.message)]),
                           key=lambda p: len(p))),
                color=discord.Color.main))
        await self.bot.conn.execute(
            'INSERT INTO guild_prefs (guild_id, prefix) VALUES ($1, $2) ON CONFLICT (guild_id) DO UPDATE SET prefix=$2',
            ctx.guild.id, new_prefix)
        await ctx.send(f'Prefix successfully changed to `{new_prefix}`')

    @commands.command()
    @commands.is_owner()
    async def sql(self, ctx, *, query: str):
        is_multistatement = query.count(';') > 1
        if is_multistatement:
            strategy = self.bot.conn.execute
        else:
            strategy = self.bot.conn.fetch

        start = time.perf_counter()
        results = await strategy(query)
        dt = (time.perf_counter() - start) * 1000.0

        rows = len(results)
        if is_multistatement or rows == 0:
            return await ctx.send(f'`{dt:.2f}ms: {results}`')

        headers = list(results[0].keys())
        await ctx.safe_send('```' + tabulate(list(list(r.values()) for r in results), headers=headers,
                                        tablefmt='pretty') + '```')

    @commands.group(name='dev')
    @commands.is_owner()
    async def dev_command_group(self, ctx):
        pass

    @dev_command_group.command(name='logs')
    @commands.is_owner()
    async def view_journal_ctl(self, ctx):
        stdout, stderr = await do_shell('journalctl -u mybot -n 300 --no-pager -o cat')
        output = stdout + stderr
        entries = list(clean_bytes(output))
        source = ShellMenu(entries, code_lang='sh', per_page=1985)
        menu = CSMenu(source, delete_message_after=True)
        await menu.start(ctx)

    @commands.command(name='edit')
    @commands.is_owner()
    async def args_edit(self, ctx, *, args: str):
        """
        Edit the bot's aspects using a command-line syntax.
        Available arguments:
            -p --presence: edits the bot's presence (playing, listening, streaming, watching, none)
            -n --nick: edits the bot's nickname for the current guild
            -s --status: edits the bot's status (dnd, idle, online, offline)
        """
        status_dict = {
            'online': discord.Status.online,
            'offline': discord.Status.offline,
            'dnd': discord.Status.dnd,
            'idle': discord.Status.idle
        }
        type_dict = {
            'playing': 0,
            'streaming': 'streaming',
            'listening': 2,
            'watching': 3,
            'none': None
        }
        updated_list = []
        parser = Arguments(add_help=False, allow_abbrev=False)
        parser.add_argument('-s', '--status', nargs='?', const='online', dest='status')
        parser.add_argument('-p', '--presence', nargs='+', dest='presence')
        parser.add_argument('-n', '--nick', nargs='?', const='None', dest='nick')
        args = parser.parse_args(shlex.split(args))
        if args.presence:
            if type_dict.get(args.presence[0]) is None:
                await self.bot.change_presence(status=ctx.me.status)
            elif type_dict.get(args.presence[0]) == 'streaming':
                args.presence.pop(0)
                await self.bot.change_presence(activity=discord.Streaming(
                    name=' '.join(args.presence), url='https://www.twitch.tv/#'))
            else:
                await self.bot.change_presence(
                    status=ctx.me.status,
                    activity=discord.Activity(
                        type=type_dict[args.presence.pop(0)], name=' '.join(args.presence)))
            updated_list.append(
                f'Changed presence to {ctx.me.activity.name if ctx.me.activity is not None else "None"}')
        if args.nick:
            await ctx.me.edit(nick=args.nick if args.nick != 'None' else None)
            updated_list.append(f'Changed nickname to {args.nick}')
        if args.status:
            await self.bot.change_presence(status=status_dict[args.status.lower()], activity=ctx.me.activity)
            updated_list.append(f'Changed status to {conf["emoji_dict"][args.status.lower()]}')
        await ctx.send(
            embed=discord.Embed(
                title='Edited bot', description='\n'.join(updated_list), color=discord.Color.main),
            delete_after=7.5
        )

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
            for filename in os.listdir('./cogs'):
                try:
                    if not filename.endswith('.py') or filename == 'dev.py':
                        continue
                    self.bot.load_extension(f'cogs.{filename[:-3]}')
                except Exception:
                    continue
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
            for filename in os.listdir('./cogs'):
                try:
                    if not filename.endswith('.py') or filename == 'dev.py':
                        continue
                    self.bot.unload_extension(f'cogs.{filename[:-3]}')
                except Exception:
                    continue
            await ctx.message.add_reaction(ctx.tick(True))
        else:
            if 'dev' in [ex.lower() for ex in extension]:
                return await ctx.send('The "dev" extension cannot be unloaded')
            for e in extension:
                self.bot.unload_extension(f'cogs.{e.lower()}')
                ls.append(e)
            await ctx.message.add_reaction(ctx.tick(True))

    @commands.command()
    @commands.is_owner()
    async def reload(self, ctx, *, extension):  # Cog loading
        extension = extension.split(' ')
        """Pulls from git and then reloads all or specified cogs"""
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
                await ctx.send(
                    f'\nThe following {pluralize("extension", errored)} errored while reloading: ' + ', '.join(errored))
            else:
                await ctx.message.add_reaction(ctx.tick(True))
        else:
            for e in extension:
                self.bot.reload_extension(f'cogs.{e.lower()}')
                errored.append(e)
            await ctx.send(f'Succesfully reloaded {pluralize("extension", errored)} {", ".join(errored)}')


def setup(bot):
    bot.add_cog(Dev(bot))
