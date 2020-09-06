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
import collections
from contextlib import suppress
import re
from datetime import datetime
import difflib

import discord
from discord.ext import commands, tasks
from humanize import naturaltime as nt

import neo

ignored_cmds = re.compile(r'\.+')

class SnipedMessage:
    def __init__(self, *, content=None, author, before=None, after=None, deleted_at):
        self.author = author
        self.deleted_at = deleted_at
        if before and after:
            diff = difflib.unified_diff(
                f'{before}\n'.splitlines(keepends=True),
                f'{after}\n'.splitlines(keepends=True))
            self.content = '```diff\n' + ''.join(diff) + '```'
        else:
            self.content = content

    def __repr__(self):
        return f"<SnipedMessage deleted_at={self.deleted_at!r} author={str(self.author)!r}>"

    def to_embed(self):
        embed = neo.Embed()
        embed.description = self.content
        embed.set_author(
            name=f"{self.author.name} - {nt(datetime.now() - self.deleted_at)}",
            icon_url=self.author.avatar_url_as(static_format='png'))
        return embed


class Events(commands.Cog):
    """Contains the listeners for the bot"""

    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        if isinstance(error, (commands.CommandNotFound,
                              commands.NotOwner,
                              neo.utils.errors.Blacklisted)):
            return  # Ignores CommandNotFound and NotOwner because they're unnecessary
        elif isinstance(error, commands.CommandOnCooldown):
            return await ctx.message.add_reaction(neo.conf['emojis']['alarm'])  # Handles Cooldowns uniquely
        do_emojis = True
        if hasattr(error, 'original'):
            error = error.original
        if settings := self.bot.user_cache.get(ctx.author.id):
            if settings.get('repr_errors'):
                error = repr(error)
            do_emojis = settings.get('error_emojis', True)
        await ctx.propagate_error(error, do_emojis=do_emojis)  # Anything else is propagated to the
        # reaction handler

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if after.content == before.content or not after.guild: return
        if self.bot.guild_cache[after.guild.id]['snipes'] is False: return
        if not self.bot.snipes.get(after.channel.id):  # Creates the snipes cache
            self.bot.snipes[after.channel.id] = {'deleted': collections.deque(list(), 100),
                                                 'edited': collections.deque(list(), 100)}
        if usr := self.bot.user_cache.get(after.author.id):
            if not usr['can_snipe']: return
        if after.content and not after.author.bot:  # Updates the snipes edit cache
            now = datetime.now()
            self.bot.snipes[after.channel.id]['edited'].append(
                SnipedMessage(
                    author=after.author,
                    before=before.content,
                    after=after.content,
                    deleted_at=now))

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        if not message.guild: return
        if self.bot.guild_cache[message.guild.id]['snipes'] is False: return
        if not self.bot.snipes.get(message.channel.id):  # Creates the snipes cache
            self.bot.snipes[message.channel.id] = {'deleted': collections.deque(list(), 100),
                                                   'edited': collections.deque(list(), 100)}
        if usr := self.bot.user_cache.get(message.author.id):
            if not usr['can_snipe']: return
        if message.content and not message.author.bot:  # Updates the snipes deleted cache
            now = datetime.now()
            self.bot.snipes[message.channel.id]['deleted'].append(
                SnipedMessage(
                    author=message.author,
                    content=message.content,
                    deleted_at=now))

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        embed = neo.Embed(
            description=f'Joined guild {guild.name} [{guild.id}]')
        embed.set_thumbnail(url=guild.icon_url_as(static_format='png'))
        embed.add_field(
            name='**Members**',  # Basic stats about the guild
            value=f'**Total:** {len(guild.members)}\n'
                  + f'**Admins:** {len([m for m in guild.members if m.guild_permissions.administrator])}\n'
                  + f'**Owner: ** {guild.owner}\n',
            inline=False)
        with suppress(Exception):
            async for a in guild.audit_logs(limit=5):  # Tries to disclose who added the bot
                if a.action == discord.AuditLogAction.bot_add:
                    action = a
                    break
            embed.add_field(
                name='**Added By**',
                value=action.user
            )

        await self.bot.pool.execute(  # Adds/updates this guild in the db using upsert syntax
            'INSERT INTO guild_prefs (guild_id, prefixes) VALUES ($1, $2)'
            'ON CONFLICT (guild_id) DO UPDATE SET prefixes=$2',
            guild.id, ['n/'])
        await self.bot.guild_cache.refresh()
        await self.bot.logging_channels.get('guild_io').send(embed=embed)
        if guild.id == 333949691962195969:
            [setattr(cmd, "enabled", False) for cmd in (
                self.bot.get_command('ui'),
                self.bot.get_command('av'),
                self.bot.get_command('em'),
                self.bot.get_command('em search'),
                self.bot.get_command('em big'),
                self.bot.get_command('resolve'))]
            commands.is_nsfw()(self.bot.get_command('g img'))
            commands.is_nsfw()(self.bot.get_command('g'))

    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
        await self.bot.pool.execute('DELETE FROM guild_prefs WHERE guild_id=$1', guild.id)
        # Removes guild from database
        embed = discord.Embed(
            description=f'Removed from guild {guild.name} [{guild.id}]',
            color=discord.Color.pornhub)  # Don't ask
        embed.set_thumbnail(url=guild.icon_url_as(static_format='png'))
        await self.bot.guild_cache.refresh()
        await self.bot.logging_channels.get('guild_io').send(embed=embed)


def setup(bot):
    bot.add_cog(Events(bot))
