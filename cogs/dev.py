"""
neo Discord bot
Copyright (C) 2020 nickofolas

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
import asyncio
import copy
import io
import os
import re
import textwrap
import time
import traceback
from contextlib import redirect_stdout, suppress
from typing import Union

import discord
import import_expression
from discord.ext import commands, flags
from tabulate import tabulate

import utils
from utils.formatters import return_lang_hl, pluralize
from utils.converters import CBStripConverter

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


def _group(iterable, page_len=50):
    pages = []
    while iterable:
        pages.append(iterable[:page_len])
        iterable = iterable[page_len:]
    return pages


def handle_eval_exc(exception, ctx):
    fmtd_exc = ''.join(traceback.format_exception(type(exception), exception, exception.__traceback__))
    formatted = ''.join(re.sub(r'File ".+",', 'File [omitted]', fmtd_exc))
    pages = _group(formatted, 1500)
    pages = [ctx.codeblock(page, 'py') for page in pages]
    ctx.bot.loop.create_task(ctx.quick_menu(pages, 1, delete_message_after=True, timeout=300))


# noinspection PyBroadException
class Dev(commands.Cog):
    """Commands made to assist with bot development"""

    def __init__(self, bot):
        self.bot = bot
        self._last_result = None

    async def cog_check(self, ctx):
        return await self.bot.is_owner(ctx.author)

    @commands.command(aliases=['sh'])
    async def shell(self, ctx, *, args: CBStripConverter):
        """Invokes the system shell,
        attempting to run the inputted command"""
        hl_lang = 'sh'
        if 'cat' in args:
            hl_lang = return_lang_hl(args)
        if 'git diff' in args:
            hl_lang = 'diff'
        async with ctx.loading(tick=False):
            stdout, stderr = await do_shell(args)
            output = stdout + stderr
            cleaned = clean_bytes(output)
            pages = _group(cleaned, 1500)
            pages = [ctx.codeblock(page, hl_lang) for page in pages]
        await ctx.quick_menu(pages, 1, delete_message_after=True, timeout=300)

    @commands.command(name='eval')
    async def eval_(self, ctx, *, body: CBStripConverter):
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
        stdout = io.StringIO()
        to_compile = f'async def func():\n{textwrap.indent(body, "  ")}'
        try:
            import_expression.exec(to_compile, env)
        except Exception as e:
            handle_eval_exc(e, ctx)
            return
        evaluated_func = env['func']
        try:
            with redirect_stdout(stdout):
                result = await evaluated_func() or ''
        except Exception as e:
            handle_eval_exc(e, ctx)
            return
        else:
            value = stdout.getvalue() or ''
            with suppress(Exception):
                await ctx.message.add_reaction(ctx.tick(True))
            self._last_result = result
            to_return = f'{value}{result}'
        if to_return:
            pages = _group(to_return, 1500)
            pages = [ctx.codeblock(page, 'py') for page in pages]
            await ctx.quick_menu(pages, 1, delete_message_after=True, timeout=300)

    @commands.command()
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
    async def sql(self, ctx, *, query: CBStripConverter):
        """Run SQL statements"""
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
        table = tabulate(list(list(r.values()) for r in results), headers=headers, tablefmt='pretty')
        await ctx.safe_send(f'```\n{table}```\nReturned {rows} {pluralize("row", rows)} in {dt:.2f}ms')

    @commands.group(name='dev', invoke_without_command=True)
    async def dev_command_group(self, ctx):
        """Some dev commands"""
        await ctx.send("We get it buddy, you're super cool because you can use the dev commands")

    @dev_command_group.command(name='delete', aliases=['del'])
    async def delete_bot_msg(self, ctx, message_ids: commands.Greedy[int]):
        for m_id in message_ids:
            converter = commands.MessageConverter()
            m = await converter.convert(ctx, str(m_id))
            if not m.author.bot:
                raise commands.CommandError('I can only delete my own messages')
            await m.delete()
        await ctx.message.add_reaction(ctx.tick(True))

    @flags.add_flag('-s', '--status', default='online', choices=['online', 'offline', 'dnd', 'idle'])
    @flags.add_flag('-p', '--presence', nargs='+', dest='presence')
    @flags.add_flag('-n', '--nick', nargs='?', const='None')
    @flags.command(name='edit')
    async def args_edit(self, ctx, **flags):
        """Edit the bot"""
        if pres := flags.get('presence'):
            if type_dict.get(pres[0]) is None:
                await self.bot.change_presence(status=ctx.me.status)
            elif type_dict.get(pres[0]) == 'streaming':
                pres.pop(0)
                await self.bot.change_presence(activity=discord.Streaming(
                    name=' '.join(pres), url='https://www.twitch.tv/#'))
            else:
                await self.bot.change_presence(
                    status=ctx.me.status,
                    activity=discord.Activity(
                        type=type_dict[pres.pop(0)], name=' '.join(pres)))
        if nick := flags.get('nick'):
            await ctx.me.edit(nick=nick if nick != 'None' else None)
        if stat := flags.get('status'):
            await self.bot.change_presence(status=status_dict[stat.lower()], activity=ctx.me.activity)
        await ctx.message.add_reaction(ctx.tick(True))

    @commands.group(invoke_without_command=True)
    async def sudo(self, ctx, target: Union[discord.Member, discord.User, None], *, command):
        """Run command as another user"""
        if not isinstance(target, (discord.Member, discord.User)):
            new_ctx = await copy_ctx(self, ctx, command, author=ctx.author)
            await new_ctx.reinvoke()
            return
        new_ctx = await copy_ctx(self, ctx, command, author=target)
        await self.bot.invoke(new_ctx)

    @sudo.command(name='in')
    async def _in(
            self, ctx,
            channel: discord.TextChannel,
            *, command):
        new_ctx = await copy_ctx(
            self, ctx, command, channel=channel)
        await self.bot.invoke(new_ctx)

    @commands.command(aliases=['die', 'kys'])
    async def reboot(self, ctx):
        """Kills all of the bot's processes"""
        response = await ctx.prompt('Are you sure you want to reboot?')
        if response:
            await self.bot.close()

    @commands.command(name='screenshot', aliases=['ss'])
    async def _website_screenshot(self, ctx, *, site):
        """Take a screenshot of a site"""
        async with ctx.typing():
            response = await self.bot.session.get('https://magmachain.herokuapp.com/api/v1', headers={'website': site})
            url = (await response.json())['snapshot']
            await ctx.send(embed=discord.Embed(colour=discord.Color.main).set_image(url=url))

    @flags.add_flag('-m', '--mode', choices=['r', 'l', 'u'], default='r')
    @flags.add_flag('-p', '--pull', action='store_true')
    @flags.add_flag('extension', nargs='*')
    @flags.command(name='extensions', aliases=['ext'])
    async def _dev_extensions(self, ctx, **flags):
        """Manage extensions"""
        mode_mapping = {'r': self.bot.reload_extension, 'l': self.bot.load_extension, 'u': self.bot.unload_extension}
        if flags.get('pull'):
            await do_shell('git pull')
        mode = mode_mapping.get(flags['mode'])
        extensions = [*self.bot.extensions.keys()] if flags['extension'][0] == '~' else flags['extension']
        for ext in extensions:
            mode(ext)
        await ctx.message.add_reaction(ctx.tick(True))
        # TODO: Write a context manager for ^ this so it doesnt always react true


def setup(bot):
    bot.add_cog(Dev(bot))
