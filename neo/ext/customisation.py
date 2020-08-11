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
import asyncio
from random import Random
from datetime import datetime
from time import time
from typing import Union
from textwrap import indent, shorten
from contextlib import suppress

import discord
from discord.ext import commands, flags
from humanize import naturaltime, naturaldate
from yarl import URL

import neo
from neo.utils.checks import is_owner_or_administrator
from neo.utils.formatters import prettify_text
from neo.utils.converters import BoolConverter, TimeConverter


class Reminder:
    def __init__(self, *, user, bot, content, deadline, conn_pool, rm_id, jump_origin):
        self.user = user
        self.content = content
        self.deadline = deadline
        self.conn_pool = conn_pool
        self.rm_id = rm_id
        self.jump_origin = jump_origin
        self.bot = bot
        self.task = bot.loop.create_task(self._do_wait(), name=f"REMINDER-{self.rm_id}")

    def __repr__(self):
        attrs = ' '.join(f"{k}={v!r}" for k, v in self.__dict__.items())
        return f"<{self.__class__.__name__} {attrs}>"

    async def _do_wait(self):
        await discord.utils.sleep_until(self.deadline)
        await self._do_remind()

    async def _do_remind(self):
        target = self.bot.get_channel(int(list(URL(self.jump_origin).parts)[3])) or self.user
        if self.bot.user_cache[self.user.id]['dm_reminders'] is True:
            target = self.user
        send_content = f"**{self.user.mention} - <{self.jump_origin}>**\n" + indent(self.content, '> ')
        await target.send(send_content, allowed_mentions=discord.AllowedMentions(users=[self.user]))
        await self.conn_pool.execute('DELETE FROM reminders WHERE id=$1 AND user_id=$2', self.rm_id, self.user.id)

class Customisation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.max_highlights = 10
        self.pending_reminders = list()
        bot.loop.create_task(self._create_first_reminders())

    @commands.command(name='settings')
    async def user_settings(self, ctx, setting_name=None, *, new_setting: Union[BoolConverter, str] = None):
        """View and edit boolean user settings"""
        if setting_name is not None and new_setting is not None:
            keys = self.bot.user_cache.get(ctx.author.id).keys()
            if setting_name not in keys:
                raise commands.CommandError(f"New setting must be one of {', '.join(keys)}")
            async with ctx.loading():
               await self.bot.pool.execute(f"UPDATE user_data SET {setting_name}=$1 WHERE user_id=$2", new_setting,
                                           ctx.author.id)
            await self.bot.user_cache.refresh()
            return
        embed = neo.Embed(title=f"""{ctx.author}'s Settings""")
        readable_settings = []
        for k, v in self.bot.user_cache[ctx.author.id].items():
            if isinstance(v, bool):
                readable_settings.append(f'{ctx.toggle(v)} **{discord.utils.escape_markdown(k)}**')
            elif isinstance(v, (list, str)) or v is None:
                continue
            else:
                readable_settings.append(f'**{discord.utils.escape_markdown(k)}** `{v}`')
        embed.description = '\n'.join(readable_settings)
        await ctx.send(embed=embed.set_thumbnail(url=ctx.author.avatar_url_as(static_format='png')))

    @commands.command(name='config', aliases=['cfg'])
    @commands.guild_only()
    @is_owner_or_administrator()
    async def _guild_config(self, ctx, setting_name=None, *, new_setting: Union[BoolConverter, str] = None):
        """View and edit boolean guild configuration options"""
        if setting_name is not None and new_setting is not None:
            keys = self.bot.guild_cache.get(ctx.guild.id).keys()
            if setting_name not in keys:
                raise commands.CommandError(f"New setting must be one of {', '.join(keys)}")
            async with ctx.loading():
               await self.bot.pool.execute(f"UPDATE guild_prefs SET {setting_name}=$1 WHERE guild_id=$2", new_setting,
                                           ctx.guild.id)
            await self.bot.guild_cache.refresh()
            return
        embed = neo.Embed(title=f"""{ctx.guild}'s Settings""")
        readable_settings = []
        for k, v in self.bot.guild_cache[ctx.guild.id].items():
            if isinstance(v, bool):
                readable_settings.append(f'{ctx.toggle(v)} **{discord.utils.escape_markdown(k)}**')
            else:
                continue
        embed.description = '\n'.join(readable_settings)
        await ctx.send(embed=embed.set_thumbnail(url=ctx.guild.icon_url_as(static_format='png')))

    @commands.group(name='prefix', invoke_without_command=True)
    async def _prefix(self, ctx):
        """Invoked by itself, it will show base prefixes, and custom prefixes for the current guild
        Its subcommands delve into customisation of said prefixes"""
        embed = neo.Embed()
        guild_data = None
        always_active = [ctx.me.mention]
        if ctx.guild:
            guild_data = self.bot.guild_cache[ctx.guild.id]
        else: # TODO: make default prefix a config value or something
            always_active.append('`n/`')
        if guild_data:
            embed.add_field(name=f'{ctx.guild}\'s prefixes',
                            value=' | '.join(map(lambda pfx: f'`{pfx}`', guild_data['prefixes'])),
                            inline=False)
        embed.description = f"**Base prefixes**\n{' | '.join(always_active)}"
        await ctx.send(embed=embed)

    @_prefix.command(name='add', aliases=['remove'])
    @is_owner_or_administrator()
    async def _modify_guild_prefixes(self, ctx, prefix):
        """Use `add`|`remove` aliases respectively to edit the list of guild prefixes."""
        current_prefixes = set(self.bot.guild_cache[ctx.guild.id]['prefixes'])
        strategy_map = {'add': current_prefixes.add, 'remove': current_prefixes.discard}
        async with ctx.loading():
            strat = strategy_map[ctx.invoked_with]
            if strat == current_prefixes.discard and len(current_prefixes) == 1:
                raise commands.CommandError('A guild must always have at least one prefix')
            strat(prefix)
            await self.bot.pool.execute(
                'UPDATE guild_prefs SET prefixes=$1 WHERE guild_id=$2',
                current_prefixes, ctx.guild.id)
            await self.bot.guild_cache.refresh()

    @commands.group(aliases=['hl'], invoke_without_command=True, ignore_extra=False)
    async def highlight(self, ctx):
        """
        Base command for keyword highlights. Run with no arguments to list your active highlights.
        """
        def format_hl(valtup):
            index, hl = valtup
            kw_full = hl.kw[:175] + ' ...' if len(hl.kw) > 175 else hl.kw
            if hl.is_regex:
                return f"`{index}` <:regex:735370786294202480> `{kw_full}`"
            return f"`{index}` `{kw_full}`"
        my_hl = list(filter(lambda hl: hl.user_id == ctx.author.id, self.bot.get_cog('HlMon').cache))
        await ctx.send(embed=neo.Embed(
            description='\n'.join(map(format_hl, enumerate(my_hl, 1)))).set_footer(
            text=f'{len(my_hl)}/10 slots used').set_author(
            name=f"{ctx.author}'s highlights", icon_url=ctx.author.avatar_url_as(static_format='png')),
                       delete_after=15.0)

    # BEGIN TODOS GROUP ~

    @commands.group(name='todo', invoke_without_command=True)
    async def todo_rw(self, ctx):
        """
        Base todo command, run with no arguments to see a list of all your active todos
        """
        query = """
        WITH enumerated AS (
        SELECT row_number() OVER (ORDER BY created_at ASC) AS rnum,
        todo.content AS cont, todo.jump_url AS jump FROM todo WHERE user_id=$1)

        SELECT FORMAT('[`%s`](%s) %s', enumerated.rnum, 
        enumerated.jump, enumerated.cont) f FROM enumerated
        """
        todos = [shorten(r['f'], width=175) for r in await self.bot.pool.fetch(query, ctx.author.id)]
        await ctx.quick_menu(
            todos, 10, 
            template=neo.Embed().set_author(
                    name=f"{ctx.author}'s todos ({len(todos):,} items)",
                    icon_url=ctx.author.avatar_url_as(static_format='png')),
            delete_on_button=True, clear_reactions_after=True)

    @todo_rw.command(name='add')
    async def create_todo(self, ctx, *, content: str):
        """
        Add an item to your todo list
        """
        query = 'INSERT INTO todo (user_id, content, jump_url, created_at) ' \
                'VALUES ($1, $2, $3, $4) RETURNING content'
        new = await self.bot.pool.fetchval(
            query, ctx.author.id, content,
            ctx.message.jump_url, datetime.utcnow())
        await ctx.send(f'`Created a new todo:`\n{new}', delete_after=5)

    @todo_rw.command(name='remove', aliases=['rm', 'delete', 'del', 'yeet'])
    async def remove_todo(self, ctx, todo_index: commands.Greedy[int]):
        """
        Remove one, or multiple todos by index
        """
        if not todo_index:
            raise commands.CommandError('Use the index of a todo [found in your list of todos] to remove it')
        query = """
        WITH enumerated AS (
        SELECT todo.content,row_number() OVER (ORDER BY created_at ASC) AS rnum FROM todo WHERE user_id=$1
        )

        DELETE FROM todo WHERE content IN (
        SELECT enumerated.content FROM enumerated WHERE enumerated.rnum=ANY($2::bigint[])
        ) RETURNING content
        """
        deleted = await self.bot.pool.fetch(query, ctx.author.id, todo_index)
        shown = [f" - {shorten(record['content'], width=175)}" for record in deleted]
        extra = f'\n *+ {len(shown[5:])} more*' if len(shown[5:]) else ''
        await ctx.send('Successfully deleted the following todos:\n{}'.format(
            '\n'.join(shown[:5]) + extra))

    @todo_rw.command(name='show', aliases=['view'])
    async def view_todo(self, ctx, todo_index: int):
        query = """
        WITH enumerated AS (
        SELECT todo.content, todo.created_at,
        row_number() OVER (ORDER BY created_at ASC) as rnum FROM todo WHERE user_id=$1)

        SELECT * FROM enumerated WHERE enumerated.rnum=$2"""
        todo = await self.bot.pool.fetchrow(query, ctx.author.id, todo_index)
        embed = neo.Embed(description=todo['content'])
        embed.set_footer(
            text=f"Created on {todo['created_at']:%a, %b, %d, %Y at %X UTC}")
        embed.set_author(
            name=f'Viewing todo #{todo_index}',
            icon_url=ctx.author.avatar_url_as(static_format='png'))
        await ctx.send(embed=embed)

    @todo_rw.command(name='clear')
    async def clear_todos(self, ctx):
        """
        Completely wipe your list of todos
        """
        conf = await ctx.prompt('Are you sure you want to clear all todos?')
        if conf:
            await self.bot.conn.execute('DELETE FROM todo WHERE user_id=$1', ctx.author.id)

    # END TODOS GROUP ~

    @commands.group(name='remind', invoke_without_command=True)
    @commands.max_concurrency(1, commands.BucketType.default)
    async def _remind(self, ctx, *, reminder: TimeConverter):
        """Add a new reminder. The first time/date found will be the one used."""
        reminder_id = int(str(int(time()))[4:])
        await self.bot.pool.execute(
            "INSERT INTO reminders (user_id, content, deadline, id, origin_jump) VALUES ($1, $2, $3, $4, $5)",
            ctx.author.id, reminder.string, reminder.time, reminder_id, ctx.message.jump_url)
        with suppress(UnboundLocalError):
            Reminder(user=ctx.author, content=reminder.string, deadline=reminder.time, 
                     bot=self.bot, conn_pool=self.bot.pool, rm_id=reminder_id, jump_origin=ctx.message.jump_url)
        pretty_time = reminder.time.strftime('%a, %b %d, %Y at %H:%M:%S')
        await ctx.send(f"{ctx.tick(True)} Reminder set for {pretty_time} with ID `{reminder_id}`")

    @_remind.command(name='list')
    async def _remind_list(self, ctx):
        """View your list of pending reminders"""
        def format_reminder(reminder):
            time = reminder['deadline'].strftime(f"%a, %b %d, %Y at %H:%M:%S %Z ({naturaltime(reminder['deadline'])})")
            return f"**{reminder['id']}: **{reminder['content']}\n{time}\n"
        reminders = [*map(
            format_reminder,
            await self.bot.pool.fetch(
                "SELECT * FROM reminders WHERE user_id=$1 ORDER BY id",
                ctx.author.id))]
        await ctx.quick_menu(reminders or ['No reminders'], 5,
                             template=neo.Embed().set_author(
                                 name=ctx.author,
                                 icon_url=ctx.author.avatar_url_as(static_format='png')),
                             delete_on_button=True, clear_reactions_after=True)

    def get_running_reminders(self):
        yield from filter(lambda task: task.get_name().startswith("REMINDER"), asyncio.all_tasks(self.bot.loop))

    @_remind.command(name='remove', aliases=['del', 'rm'])
    async def _remind_remove(self, ctx, items: commands.Greedy[int]):
        """Remove one, or many reminders by their unique ID"""
        running = [*self.get_running_reminders()]
        [task.cancel() for task in running if task.get_name().endswith(tuple(map(str, items)))]
        deleted = await self.bot.pool.fetch(
            "DELETE FROM reminders WHERE id=ANY($1::bigint[]) AND user_id=$2 RETURNING content",
            items, ctx.author.id)
        await ctx.send('Cancelled reminders:\n{}'.format('\n'.join(f" - {r['content']}" for r in deleted)))

    @_remind.command(name='clear')
    async def _remind_clear(self, ctx):
        """Cancels all of your active reminders"""
        confirm = await ctx.prompt('Are you sure you want to cancel all reminders?')
        if confirm:
            cancelled = await self.bot.pool.fetch(
                'DELETE FROM reminders WHERE user_id=$1 RETURNING id', ctx.author.id)
            [task.cancel() for task in self.get_running_reminders() if 
             task.get_name().endswith((*map(lambda r: str(r['id']), cancelled),))]

    async def _create_first_reminders(self):
        await self.bot.wait_until_ready()
        for record in await self.bot.pool.fetch("SELECT * FROM reminders"):
            Reminder(user=self.bot.get_user(record['user_id']), content=record['content'],
                deadline=record['deadline'], bot=self.bot, conn_pool=self.bot.pool,
                rm_id=record['id'], jump_origin=record['origin_jump'])

    def cog_unload(self):
        [task.cancel() for task in self.get_running_reminders()]


def setup(bot):
    bot.add_cog(Customisation(bot))
