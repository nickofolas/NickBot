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

import asyncpg
import discord
from discord.ext import commands, tasks

from utils.config import conf

ignored_cmds = re.compile(r'\.+')


def hl_checks_one(c, message):
    predicates = []
    if c[2]:
        predicates.append(message.guild.id not in c[2])
    predicates.append(not re.search(re.compile(r'([a-zA-Z0-9]{24}\.[a-zA-Z0-9]{6}\.[a-zA-Z0-9_\-]{27}|mfa\.['
                                               r'a-zA-Z0-9_\-]{84})'), message.content))
    return all(predicates)


async def build_highlight_embed(match, message):
    context_list = []
    async for m in message.channel.history(limit=5):
        avatar_index = m.author.default_avatar.value
        hl_underline = m.content.replace(match.group(0), f'**__{match.group(0)}__**')
        repl = r'<a?:\w*:\d*>'
        context_list.append(
            f"{conf['default_discord_users'][avatar_index]} **{m.author.name}:** {re.sub(repl, ':question:', hl_underline)}")
    context_list = reversed(context_list)
    embed = discord.Embed(
        title=f'A word has been highlighted!',
        description='\n'.join(context_list) + f'\n[Jump URL]({message.jump_url})',
        color=discord.Color.main)
    embed.timestamp = message.created_at
    return embed


def check_last_send(bot, message, user):
    if not (msg := discord.utils.get(bot.cached_messages, channel=message.channel, author=user)):
        return True
    return (message.created_at - msg.created_at).total_seconds() > 60


def hl_send_predicates(alerted, message):
    preds = [alerted in message.guild.members,
             alerted.id != message.author.id,
             message.channel.permissions_for(message.guild.get_member(alerted.id)).read_messages,
             not message.author.bot]
    return all(preds)


# noinspection PyCallingNonCallable
class Events(commands.Cog):
    """Contains the listeners for the bot"""

    def __init__(self, bot):
        self.bot = bot
        self.hl_mailer.start()
        self.hl_queue = list()
        self.hl_cache = []
        self.update_hl_cache.start()

    def cog_unload(self):
        self.hl_mailer.cancel()
        self.update_hl_cache.cancel()
        self.hl_cache = []

    @tasks.loop(seconds=10)
    async def hl_mailer(self):  # Flushes the highlights queue every 10 seconds, delivering all messages
        for person, embed in set(self.hl_queue):
            try:
                await person.send(embed=embed)
                await asyncio.sleep(0.25)
            except Exception:  # In case we can't DM them
                continue
        self.hl_queue = list()  # We're done with this queue, so reset it

    @tasks.loop(minutes=1.0)
    async def update_hl_cache(self):  # Keeps the cache of highlights up to date
        await self.build_hl_cache()

    @hl_mailer.before_loop
    @update_hl_cache.before_loop
    async def before_task_loops(self):  # Makes sure that the bot is ready before starting any loops
        await self.bot.wait_until_ready()

    async def build_hl_cache(self):
        await self.bot.wait_until_ready()  # Just for safety
        self.hl_cache = []
        fetched = await self.bot.conn.fetch('SELECT user_id, kw, exclude_guild FROM highlights')
        for rec in fetched:  # Loops over every Record in the highlights db, and adds it to the cache
            i = list(tuple(rec))
            i[1] = re.compile(i[1], re.I)
            i = tuple(i)
            self.hl_cache.append(i)

    # Message events
    @commands.Cog.listener()
    async def on_message(self, message):
        await self.bot.wait_until_ready()
        for c in self.hl_cache:
            with suppress(AttributeError, UnboundLocalError):
                if match := re.search(c[1], message.content):  # Makes sure there's actually a match
                    if not hl_checks_one(c, message):
                        continue
                    alerted = self.bot.get_user(c[0])
                    if not check_last_send(self.bot, message, alerted):
                        continue
                    embed = await build_highlight_embed(match, message)  # Builds the embed that'll be delivered
                    if hl_send_predicates(alerted, message):  # Checks that the predicates for sending are satisfied
                        if len(self.hl_queue) < 40 and [i[0] for i in self.hl_queue].count(alerted) < 5:
                            # Applies a final set of predicates to make sure that the queue's size is adequate
                            self.hl_queue.append((alerted, embed))  # Adds the highlight to the queue

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        if isinstance(error, (commands.CommandNotFound, commands.NotOwner)):
            return  # Ignores CommandNotFound and NotOwner because they're unnecessary
        elif isinstance(error, commands.CommandOnCooldown):
            return await ctx.message.add_reaction(conf['emoji_suite']['alarm'])  # Handles Cooldowns uniquely
        await ctx.propagate_to_eh(self.bot, ctx, error)  # Anything else is propagated to the reaction handler

    @commands.Cog.listener()
    async def on_command(self, ctx):
        with suppress(asyncpg.exceptions.UniqueViolationError):
            await self.bot.conn.execute('INSERT INTO user_data (user_id) VALUES ($1)', ctx.author.id)
            # Adds people to the user_data table whenever they execute their first command

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if after.content == before.content:
            return
        if not self.bot.snipes.get(after.channel.id):  # Creates the snipes cache
            self.bot.snipes[after.channel.id] = {'deleted': collections.deque(list(), 100),
                                                 'edited': collections.deque(list(), 100)}
        if after.content and not after.author.bot:  # Updates the snipes edit cache
            self.bot.snipes[after.channel.id]['edited'].append((before, after, datetime.utcnow()))

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        if not self.bot.snipes.get(message.channel.id):  # Creates the snipes cache
            self.bot.snipes[message.channel.id] = {'deleted': collections.deque(list(), 100),
                                                   'edited': collections.deque(list(), 100)}
        if message.content and not message.author.bot:  # Updates the snipes deleted cache
            self.bot.snipes[message.channel.id]['deleted'].append((message, datetime.utcnow()))

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        embed = discord.Embed(
            description=f'Joined guild {guild.name} [{guild.id}]',
            color=discord.Color.main)
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

        await self.bot.conn.execute(  # Adds/updates this guild in the db using upsert syntax
            'INSERT INTO guild_prefs (guild_id, prefix) VALUES ($1, $2) ON CONFLICT (guild_id) DO UPDATE SET prefix=$2',
            guild.id, 'n/')
        await self.bot.logging_channels.get('guild_io').send(embed=embed)

    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
        await self.bot.conn.execute('DELETE FROM guild_prefs WHERE guild_id=$1', guild.id)
        # Removes guild from database
        embed = discord.Embed(
            description=f'Removed from guild {guild.name} [{guild.id}]',
            color=discord.Color.pornhub)  # Don't ask
        embed.set_thumbnail(url=guild.icon_url_as(static_format='png'))
        await self.bot.logging_channels.get('guild_io').send(embed=embed)


def setup(bot):
    bot.add_cog(Events(bot))
