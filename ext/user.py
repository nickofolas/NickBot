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
from discord.ext import commands, flags

from utils.checks import check_member_in_guild
from utils.formatters import prettify_text
from utils.converters import BoolConverter


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
                await self.bot.conn.execute(f"UPDATE user_data SET {setting_name}=$1 WHERE user_id=$2", new_setting,
                                            ctx.author.id)
            await self.bot.build_user_cache()
            return
        embed = discord.Embed(title=f"""{ctx.author}'s Settings""", color=discord.Color.main)
        readable_settings = list()
        for k, v in self.bot.user_cache[ctx.author.id].items():
            if isinstance(v, bool):
                readable_settings.append(f'**{discord.utils.escape_markdown(k)}** {ctx.tick(v)}')
            elif isinstance(v, list) or v is None:
                continue
            else:
                readable_settings.append(f'**{discord.utils.escape_markdown(k)}** `{v}`')
        embed.description = '\n'.join(readable_settings)
        await ctx.send(embed=embed.set_thumbnail(url=ctx.author.avatar_url_as(static_format='png')))

    # END USER SETTINGS ~

    @commands.group(aliases=['hl'], invoke_without_command=True)
    async def highlight(self, ctx):
        """
        Base command for keyword highlights. Run with no arguments to list your active highlights.
        """
        hl_list = [f"`{c}` {'<:regex:718943797915943054>' if h.is_regex else ''} {h.kw}" for c, h in enumerate([
            h for h in self.bot.get_cog("HlMon").cache if h.user_id==ctx.author.id], 1)]
        await ctx.send(embed=discord.Embed(
            description='\n'.join(hl_list), color=discord.Color.main).set_footer(
            text=f'{len(hl_list)}/10 slots used'), delete_after=10.0)

    # BEGIN TODOS GROUP ~

    @commands.group(name='todo', invoke_without_command=True)
    async def todo_rw(self, ctx):
        """
        Base todo command, run with no arguments to see a list of all your active todos
        """
        todo_list = []
        fetched = [(rec['content'], rec['jump_url']) for rec in
                   await self.bot.conn.fetch("SELECT content, jump_url from todo WHERE user_id=$1", ctx.author.id)]
        for count, value in enumerate(fetched, 1):
            todo_list.append(f'[`{count}`]({value[1]}) {value[0]}')
        if not todo_list:
            todo_list.append('No todos')
        await ctx.quick_menu(
            todo_list, 10,
            template=discord.Embed(
                color=discord.Color.main).set_author(
                name=f"{ctx.author}'s todos", icon_url=ctx.author.avatar_url_as(static_format='png')),
            delete_message_after=True)

    @todo_rw.command(name='add')
    async def create_todo(self, ctx, *, content: str):
        """
        Add an item to your todo list
        """
        await self.bot.conn.execute('INSERT INTO todo VALUES ($1, $2, $3)',
            ctx.author.id, content, ctx.message.jump_url)
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
