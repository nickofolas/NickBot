import asyncio
import collections
from contextlib import suppress
import re
from datetime import datetime

import aiosqlite as asq
import asyncpg
import discord
from discord.ext import commands, tasks

from utils.config import conf

ignored_cmds = re.compile(r'\.+')


# noinspection PyCallingNonCallable
class Events(commands.Cog):
    """Contains the listeners for the bot"""

    def __init__(self, bot):
        self.bot = bot
        self.hl_mailer.start()
        self.update_hl_cache.start()
        self.hl_queue = list()
        self.bot.loop.create_task(self.build_hl_cache())

    def cog_unload(self):
        self.hl_mailer.cancel()
        self.update_hl_cache.cancel()

    @tasks.loop(seconds=10)
    async def hl_mailer(self):
        for person, embed in set(self.hl_queue):
            try:
                await person.send(embed=embed)
                await asyncio.sleep(0.25)
            except Exception:
                continue
        self.hl_queue = list()

    @tasks.loop(minutes=1.0)
    async def update_hl_cache(self):
        await self.build_hl_cache()

    @hl_mailer.before_loop
    @update_hl_cache.before_loop
    async def before_task_loops(self):
        await self.bot.wait_until_ready()

    # Provides general command error messages
    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        if isinstance(error, (commands.CommandNotFound, commands.NotOwner)):
            return
        await ctx.propagate_to_eh(self.bot, ctx, error)

    async def build_hl_cache(self):
        await self.bot.wait_until_ready()
        temp_cache = []
        fetched = await self.bot.conn.fetch('SELECT user_id, kw, exclude_guild FROM highlights')
        for rec in fetched:
            i = list(tuple(rec))
            i[1] = re.compile(i[1], re.I)
            i = tuple(i)
            temp_cache.append(i)
        self.hl_cache = set(temp_cache)

    @commands.Cog.listener()
    async def on_command(self, ctx):
        with suppress(asyncpg.exceptions.UniqueViolationError):
            await self.bot.conn.execute('INSERT INTO user_data (user_id) VALUES ($1)', ctx.author.id)

    # Message events
    @commands.Cog.listener()
    async def on_message(self, message):
        await self.bot.wait_until_ready()
        if not hasattr(self, 'hl_cache'):
            return
        for c in self.hl_cache:
            if match := re.search(c[1], message.content):
                if c[2]:
                    if str(message.guild.id) in c[2].split(','):
                        continue
                if re.search(re.compile(r'([a-zA-Z0-9]{24}\.[a-zA-Z0-9]{6}\.[a-zA-Z0-9_\-]{27}|mfa\.[a-zA-Z0-9_\-]{84})'), message.content):
                    continue
                alerted = self.bot.get_user(c[0])
                context_list = []
                async for m in message.channel.history(limit=5):
                    avatar_index = m.author.default_avatar.value
                    hl_underline = m.content.replace(match.group(0), f'**__{match.group(0)}__**')
                    repl = r'<a?:\w*:\d*>'
                    context_list.append(f"{conf['default_discord_users'][avatar_index]} **{m.author.name}:** {re.sub(repl, ':question:', hl_underline)}")
                context_list = reversed(context_list)
                embed = discord.Embed(
                    title=f'A word has been highlighted!',
                    description='\n'.join(context_list) + f'\n[Jump URL]({message.jump_url})',
                    color=discord.Color.main)
                embed.timestamp = message.created_at
                if (
                    alerted in message.guild.members and alerted.id != message.author.id and message.channel
                        .permissions_for(message.guild.get_member(alerted.id)).read_messages and not message.author.bot
                ):
                    if len(self.hl_queue) < 40 and [i[0] for i in self.hl_queue].count(alerted) < 5:
                        self.hl_queue.append((alerted, embed))

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if after.content != before.content:
            await self.bot.process_commands(after)
        if not self.bot.snipes.get(after.channel.id):
            self.bot.snipes[after.channel.id] = {'deleted': collections.deque(list(), 5), 'edited': collections.deque(list(), 5)}
        if after.content and not after.author.bot:
            self.bot.snipes[after.channel.id]['edited'].append((before, after, datetime.utcnow()))

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        if not self.bot.snipes.get(message.channel.id):
            self.bot.snipes[message.channel.id] = {'deleted': collections.deque(list(), 5), 'edited': collections.deque(list(), 5)}
        if message.content and not message.author.bot:
            self.bot.snipes[message.channel.id]['deleted'].append((message, datetime.utcnow()))
        # Adds the message to the dict of messages for sniping

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        embed = discord.Embed(
            description=f'Joined guild {guild.name} [{guild.id}]',
            color=discord.Color.main)
        embed.set_thumbnail(url=guild.icon_url_as(static_format='png'))
        embed.add_field(
            name='**Members**',
            value=f'**Total:** {len(guild.members)}\n'
            + f'**Admins:** {len([m for m in guild.members if m.guild_permissions.administrator])}\n'
            + f'**Owner: ** {guild.owner}\n',
            inline=False)
        with suppress(Exception):
            embed.add_field(
                name='**Guild Invite**',
                value=(await guild.text_channels[0].create_invite()))

        await self.bot.conn.execute(
            'INSERT INTO guild_prefs (guild_id, prefix) VALUES ($1, $2) ON CONFLICT (guild_id) DO UPDATE SET prefix=$2',
            guild.id, 'n/')
        await (await self.bot.application_info()).owner.send(embed=embed)

    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
        await self.bot.conn.execute('DELETE FROM guild_prefs WHERE guild_id=$1', guild.id)


def setup(bot):
    bot.add_cog(Events(bot))
