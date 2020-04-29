import math
from datetime import datetime
import re
import asyncio

import unidecode as ud
import discord
from discord.ext import commands, tasks
import aiosqlite as asq

from utils.context import Context

ignored_cmds = re.compile(r'\.+')


def round_up(n, decimals=0):
    multiplier = 10**decimals
    return math.ceil(n * multiplier) / multiplier


class Listeners(commands.Cog):
    """Contains the listeners for the bot"""

    def __init__(self, bot):
        self.bot = bot
        self.status_updater.start()
        self.hl_mailer.start()
        self.update_hl_cache.start()
        self.hl_msgs = list()

    def cog_unload(self):
        self.status_updater.cancel()
        self.hl_mailer.cancel()

    @tasks.loop(minutes=5.0)
    async def status_updater(self):
        if not self.bot.persistent_status:
            await self.bot.change_presence(
                activity=discord.Activity(
                    type=discord.ActivityType.watching,
                    name=f"{len(self.bot.guilds):,} servers | {len(self.bot.users):,} members"))

    @tasks.loop(seconds=10)
    async def hl_mailer(self):
        for person, embed in set(self.hl_msgs):
            await person.send(embed=embed)
            await asyncio.sleep(0.25)
        self.hl_msgs = list()

    @tasks.loop(minutes=1.0)
    async def update_hl_cache(self):
        await self.build_hl_cache()

    @hl_mailer.before_loop
    @status_updater.before_loop
    @update_hl_cache.before_loop
    async def before_task_loops(self):
        await self.bot.wait_until_ready()

    # Provides general command error messages
    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        if ignored_cmds.search(ctx.invoked_with):
            return
        if not isinstance(error, commands.CommandOnCooldown):
            ctx.command.reset_cooldown(ctx)
        if isinstance(error, commands.CommandNotFound):
            return
        await ctx.propagate_to_eh(self.bot, ctx, error)

    async def build_hl_cache(self):
        self.hl_cache = []
        async with asq.connect('database.db') as db:
            async with db.execute('SELECT user_id, kw, exclude_guild FROM highlights') as cur:
                async for c in cur:
                    c[1] = re.compile(c[1], re.I)
                    self.hl_cache.append(c)

    @commands.Cog.listener()
    async def on_command(self, ctx):
        async with asq.connect('./database.db') as db:
            attempt = await db.execute('SELECT * FROM user_data WHERE user_id=$1', (ctx.author.id,))
            fetch_try = await attempt.fetchall()
            if fetch_try:
                return
            else:
                await db.execute('INSERT INTO user_data(user_id) VALUES ($1)', (ctx.author.id,))
                await db.commit()

    # Message events
    @commands.Cog.listener()
    async def on_message(self, message):
        await self.bot.wait_until_ready()
        if re.search(re.compile(r'([a-zA-Z0-9]{24}\.[a-zA-Z0-9]{6}\.[a-zA-Z0-9_\-]{27}|mfa\.[a-zA-Z0-9_\-]{84})'), message.content) or not hasattr(self, 'hl_cache'):
            return
        for c in self.hl_cache:
            if match := re.search(c[1], message.content):
                if c[2]:
                    if str(message.guild.id) in c[2].split(','):
                        continue
                alerted = self.bot.get_user(c[0])
                context_list = []
                async for m in message.channel.history(limit=5):
                    context_list.append(f"> **{m.author.name}:** {m.content.replace(match.group(0), f'__{match.group(0)}__')}")
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
                    if len(self.hl_msgs) < 40 and [i[0] for i in self.hl_msgs].count(alerted) < 5:
                        self.hl_msgs.append((alerted, embed))

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        await self.bot.process_commands(after)

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        self.bot.deleted[
            message.channel.
            id] = (message, datetime.utcnow())
        # Adds the message to the dict of messages for sniping

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        await self.bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name=f"{len(self.bot.guilds):,} servers | {len(self.bot.users):,} members"))
        embed = discord.Embed(
            title='',
            description=f'Joined guild {guild.name}',
            color=discord.Color.main)
        embed.set_thumbnail(url=guild.icon_url_as(static_format='png'))
        embed.add_field(
            name='**Members**',
            value=f'**Total:** {len(guild.members)}\n'
            + f'**Admins:** {len([m for m in guild.members if m.guild_permissions.administrator])}\n'
            + f'**Owner: ** {guild.owner}\n',
            inline=False)

        try:
            embed.add_field(
                name='**Guild Invite**',
                value=(await guild.text_channels[0].create_invite()))
        except Exception:
            pass

        async with asq.connect('./database.db') as db:
            res = await db.execute("UPDATE guild_prefs SET prefix=$1 WHERE guild_id=$2", ('n/', guild.id))
            if res.rowcount < 1:
                await db.execute("INSERT INTO guild_prefs (guild_id, prefix) VALUES ($1, $2)", (guild.id, 'n/'))
            await db.commit()

        await guild.get_member(self.bot.user.id).edit(nick='Nick of O-Bot [n/]')
        '''
        try:
            if 'Muted' not in [r.name for r in guild.roles]:
                muterole = await guild.create_role(name='Muted')

                for channel in guild.channels:
                    await channel.set_permissions(
                        muterole, send_messages=False, add_reactions=False)
        except Exception as e:
            print(e)
        '''
        await (await self.bot.application_info()).owner.send(embed=embed)

    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
        await self.bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name=f"{str(len(self.bot.guilds))} servers | {len(self.bot.users)} members"))

        async with asq.connect('./database.db') as db:
            await db.execute("DELETE FROM guild_prefs WHERE guild_id=$1", (guild.id,))
            await db.commit()


def setup(bot):
    bot.add_cog(Listeners(bot))
