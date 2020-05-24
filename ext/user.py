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
import re
import string
import pprint
from typing import Union

import discord
from discord.ext import commands

from utils.checks import check_member_in_guild
from utils.formatters import prettify_text
from utils.converters import BoolConverter


def check_hl_regex(highlight_kw):
    check_re = re.compile(fr'{highlight_kw}', re.I)
    if len(highlight_kw) < 3:
        raise commands.CommandError(
            'Highlights must be more than 2 characters long')
    if '|' in highlight_kw:
        raise commands.CommandError('This trigger uses a blocked character')
    for i in ('afssafasfa', '12421', '\n', ' ', string.ascii_letters, string.digits):
        if re.search(check_re, i):
            raise commands.CommandError('This trigger is too general')


def index_check(command_input):
    try:
        int(command_input[0])
    except ValueError:
        return False
    else:
        return True


class User(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.max_highlights = 10

    # START USER SETTINGS ~
    @commands.command(name='settings')
    async def user_settings(self, ctx, setting_name=None, *, new_setting: Union[BoolConverter, str] = None):
        if setting_name is not None and new_setting is not None:
            keys = self.bot.user_cache.get(ctx.author.id).keys()
            if setting_name not in keys:
                raise commands.CommandError(f"New setting must be one of {', '.join(keys)}")
            async with ctx.loading():
                await self.bot.conn.execute(f"UPDATE user_data SET {setting_name}=$1 WHERE user_id=$2", new_setting, ctx.author.id)
            await self.bot.build_user_cache()
            return
        cur = dict((await self.bot.conn.fetch("SELECT * FROM user_data WHERE user_id=$1", ctx.author.id))[0])
        embed = discord.Embed(title=f"""{self.bot.get_user(cur.pop("user_id"))}'s Settings""", color=discord.Color.main)
        readable_settings = list()
        for k, v in cur.items():
            if isinstance(v, bool):
                readable_settings.append(f'**{discord.utils.escape_markdown(k)}** {ctx.tick(v)}')
            else:
                readable_settings.append(f'**{discord.utils.escape_markdown(k)}** `{v}`')
        embed.description = '\n'.join(readable_settings)
        await ctx.send(embed=embed.set_thumbnail(url=ctx.author.avatar_url_as(static_format='png')))

    # END USER SETTINGS ~
    # BEGIN HIGHLIGHTS GROUP ~

    @commands.group(aliases=['hl'], invoke_without_command=True)
    async def highlight(self, ctx):
        """
        Base command for keyword highlights. Run with no arguments to list your active highlights.
        """
        hl_list = []
        fetched = [rec['kw'] for rec in
                   await self.bot.conn.fetch('SELECT kw FROM highlights WHERE user_id=$1', ctx.author.id)]
        for i in range(self.max_highlights):
            to_append = f"`{(i + 1)}` {fetched[i]}" if i < len(fetched) else ''
            hl_list.append(to_append)
        await ctx.send(embed=discord.Embed(
            description='\n'.join(hl_list), color=discord.Color.main).set_footer(
            text=f'{len(fetched)}/{self.max_highlights} slots used'))

    @highlight.command()
    async def add(self, ctx, *, highlight_words):
        """
        Add a new highlight! When a highlighted word is used, you'll get notified!
        If desired, the highlight can be made quite granular, as regex patterns are
        supported.
        NOTE: It may take up to a minute for a new highlight to take effect
        """
        check_hl_regex(highlight_words)
        active = await self.bot.conn.fetch('SELECT kw FROM highlights WHERE user_id=$1', ctx.author.id)
        if len(active) >= self.max_highlights:
            raise commands.CommandError(f'You may only have {self.max_highlights} highlights at a time')
        if highlight_words in [rec['kw'] for rec in active]:
            raise commands.CommandError('You already have a highlight with this trigger')
        await self.bot.conn.execute(
            'INSERT INTO highlights(user_id, kw) VALUES ( $1, $2 )',
            ctx.author.id, fr"{highlight_words}")
        await ctx.message.add_reaction(ctx.tick(True))

    @highlight.command(name='exclude', aliases=['mute', 'ignore', 'exc'])
    async def exclude_guild(self, ctx, highlight_index, guild_id: int = None):
        """Add and remove guilds to be ignored from highlight notifications.
        Specify which highlight to ignore via its index
            - To ignore from the current guild, pass no further arguments
            - To ignore from another guild, pass that guild's id
        If the specified guild is not being ignored, then it will be added to the list
        of ignored guilds
            - If the specified guild is already being ignored, running the command,
            and passing that guild a second time will remove it from the list
        NOTE: It may take up to a minute for this to take effect"""
        if not index_check(highlight_index):
            raise commands.CommandError('Specify a highlight by its index (found in your list of highlights)')
        highlight_index = int(highlight_index)
        guild_id = guild_id or ctx.guild.id
        iterable_hls = [(rec['kw'], rec['exclude_guild'])
                        for rec in
                        await self.bot.conn.fetch(
                            'SELECT kw, exclude_guild FROM highlights WHERE user_id=$1', ctx.author.id)]
        current = iterable_hls[highlight_index - 1][1]
        if current and guild_id in current:
            await self.bot.conn.execute('UPDATE highlights SET exclude_guild = array_remove(exclude_guild, $1) WHERE '
                                        'user_id=$2 AND kw=$3',
                                        guild_id, ctx.author.id, iterable_hls[highlight_index - 1][0])
        else:
            await self.bot.conn.execute('UPDATE highlights SET exclude_guild = array_append(exclude_guild, $1) WHERE '
                                        'user_id=$2 AND kw=$3',
                                        guild_id, ctx.author.id, iterable_hls[highlight_index - 1][0])
        await ctx.message.add_reaction(ctx.tick(True))

    @highlight.command(name='info')
    async def view_highlight_info(self, ctx, highlight_index):
        """Display info on what triggers a specific highlight, or what guilds are muted from it"""
        if not index_check(highlight_index):
            raise commands.CommandError('Specify a highlight by its index (found in your list of highlights)')
        highlight_index = int(highlight_index)
        hl_data = tuple(
            (await self.bot.conn.fetch('SELECT * FROM highlights WHERE user_id=$1', ctx.author.id))[
                highlight_index - 1])
        ex_guild_display = f"**Ignored Guilds** {', '.join([self.bot.get_guild(i).name for i in hl_data[2]])}" if \
            hl_data[2] else ''
        embed = discord.Embed(
            description=f'**Triggered by** "{hl_data[1]}"\n{ex_guild_display}',
            color=discord.Color.main)
        await ctx.send(embed=embed)

    @highlight.command(name='remove', aliases=['rm', 'delete', 'del', 'yeet'])
    async def remove_highlight(self, ctx, highlight_index: commands.Greedy[int]):
        """
        Remove one, or multiple highlights by index
        NOTE: It may take up to a minute for this to take effect
        """
        if not highlight_index:
            raise commands.CommandError('Use the index of a highlight (found in your list of highlights) to remove it')
        fetched = [rec['kw'] for rec in
                   await self.bot.conn.fetch("SELECT kw from highlights WHERE user_id=$1", ctx.author.id)]
        for num in highlight_index:
            await self.bot.conn.execute('DELETE FROM highlights WHERE user_id=$1 AND kw=$2',
                                        ctx.author.id, fetched[num - 1])
        await ctx.message.add_reaction(ctx.tick(True))

    @highlight.command(name='clear', aliases=['yeetall'])
    async def clear_highlights(self, ctx):
        """
        Completely wipe your list of highlights
        NOTE: It may take up to a minute for this to take effect
        """
        conf = await ctx.prompt('Are you sure you want to clear all highlights?')
        if conf:
            await self.bot.conn.execute('DELETE FROM highlights WHERE user_id=$1', ctx.author.id)

    @highlight.command(name='import')
    @check_member_in_guild(292212176494657536)
    @commands.max_concurrency(1, commands.BucketType.channel)
    async def import_from_highlight(self, ctx):
        """
        Import your highlights from the <@292212176494657536> bot (can only be run in shared guilds)
        Imports every highlight it can while maintaining the maximum number of slots.
        """
        await ctx.send('Please call your lists of highlights from <@292212176494657536>')
        msg = await self.bot.wait_for('message',
                                      check=lambda m:
                                      m.author.id == 292212176494657536
                                      and m.embeds and str(ctx.author.id) in
                                      m.embeds[0].author.icon_url and m.channel.id == ctx.channel.id,
                                      timeout=15.0)
        e = msg.embeds[0]
        if e.title != 'Triggers':
            return await ctx.send('Failed to find a response with your highlights')
        imported_highlights = e.description.splitlines()
        added = 0
        for new_hl in imported_highlights:
            try:
                check_hl_regex(new_hl)
            except commands.CommandError:
                continue
            active = await self.bot.conn.fetch('SELECT kw FROM highlights WHERE user_id=$1', ctx.author.id)
            if len(active) >= self.max_highlights:
                break
            if new_hl in [rec['kw'] for rec in active]:
                raise commands.CommandError('You already have a highlight with this trigger')
            await self.bot.conn.execute(
                'INSERT INTO highlights(user_id, kw) VALUES ( $1, $2 )',
                ctx.author.id, fr"{new_hl}")
            added += 1
        await ctx.send(f'Imported {added} highlights')

    @highlight.group(invoke_without_command=True, name='dev')
    @commands.is_owner()
    async def hl_dev(self, ctx):
        pass

    @hl_dev.command(name='queue')
    @commands.is_owner()
    async def view_hl_queue(self, ctx):
        await ctx.safe_send(pprint.pformat(self.bot.get_cog('Events').hl_queue))

    @hl_dev.command(name='cache')
    @commands.is_owner()
    async def view_hl_cache(self, ctx):
        await ctx.safe_send(pprint.pformat(self.bot.get_cog('Events').hl_cache))

    @hl_dev.command(name='build')
    @commands.is_owner()
    async def hl_cache_build_cmd(self, ctx):
        await self.bot.get_cog('Events').build_hl_cache()
        await ctx.message.add_reaction(ctx.tick(True))

    # END HIGHLIGHTS GROUP ~
    # BEGIN TODOS GROUP ~

    @commands.group(name='todo', invoke_without_command=True)
    async def todo_rw(self, ctx):
        """
        Base todo command, run with no arguments to see a list of all your active todos
        """
        todo_list = []
        fetched = [rec['content'] for rec in
                   await self.bot.conn.fetch("SELECT content from todo WHERE user_id=$1", ctx.author.id)]
        for count, value in enumerate(fetched, 1):
            todo_list.append(f'`{count}` {value}')
        if not todo_list:
            todo_list.append('No todos')
        await ctx.quick_menu(todo_list, 10,
                             template=discord.Embed(
                                 color=discord.Color.main).set_author(
                                 name=f"{ctx.author}'s todos", icon_url=ctx.author.avatar_url_as(static_format='png')),
                             delete_message_after=True)

    @todo_rw.command(name='add')
    async def create_todo(self, ctx, *, content: str):
        """
        Add an item to your todo list
        """
        await self.bot.conn.execute('INSERT INTO todo VALUES ($1, $2)', ctx.author.id, content)
        await ctx.message.add_reaction(ctx.tick(True))

    @todo_rw.command(name='remove', aliases=['rm', 'delete', 'del', 'yeet'])
    async def remove_todo(self, ctx, todo_index: commands.Greedy[int]):
        """
        Remove one, or multiple todos by index
        """
        if not todo_index:
            raise commands.CommandError('Use the index of a todo (found in your list of todos) to remove it')
        fetched = [rec['content'] for rec in
                   await self.bot.conn.fetch("SELECT content from todo WHERE user_id=$1", ctx.author.id)]
        for num in todo_index:
            await self.bot.conn.execute('DELETE FROM todo WHERE user_id=$1 AND content=$2',
                                        ctx.author.id, fetched[num - 1])
        await ctx.message.add_reaction(ctx.tick(True))

    @todo_rw.command(name='clear')
    async def clear_todos(self, ctx):
        """
        Completely wipe your list of todos
        """
        conf = await ctx.prompt('Are you sure you want to clear all todos?')
        if conf:
            await self.bot.conn.execute('DELETE FROM todo WHERE user_id=$1', ctx.author.id)

    # END TODOS GROUP ~


def setup(bot):
    bot.add_cog(User(bot))
