import math
from datetime import datetime
import re

import unidecode as ud
import discord
from discord.ext import commands, tasks
import aiosqlite as asq

from utils.context import Context

me = re.compile(r'n+[i¡!]+c+[kh]+((of)?olas)?', re.I)
ignored_cmds = re.compile(r'\.+')


def round_up(n, decimals=0):
    multiplier = 10**decimals
    return math.ceil(n * multiplier) / multiplier


class Listeners(commands.Cog):
    """Contains the listeners for the bot"""

    def __init__(self, bot):
        self.bot = bot
        self.status_updater.start()

    def cog_unload(self):
        self.status_updater.cancel()

    @tasks.loop(minutes=5.0)
    async def status_updater(self):
        if not self.bot.persistent_status:
            await self.bot.change_presence(
                activity=discord.Activity(
                    type=discord.ActivityType.watching,
                    name=f"{len(self.bot.guilds):,} servers | {len(self.bot.users):,} members"))

    @status_updater.before_loop
    async def before_status_updater(self):
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


    '''
    @commands.Cog.listener()
    async def on_socket_response(self, m):
        try:
            try:
                self.bot.socket_stats[m.get('t')] += 1
            except KeyError:
                self.bot.socket_stats[m.get('t')] = 1
        except Exception:
            return
    '''


    # Message events
    @commands.Cog.listener()
    async def on_message(self, message):
        await self.bot.wait_until_ready()
        async with Context.ExHandler(exception_type=AttributeError), asq.connect('database.db') as db:
            async with db.execute('SELECT user_id, kw, exclude_guild FROM highlights') as cur:
                async for c in cur:
                    if c[1].lower() in message.content.lower() and not\
                     message.author.bot:
                        if c[2]:
                            if str(message.guild.id) in c[2].split(','):
                                continue
                        alerted = self.bot.get_user(c[0])
                        embed = discord.Embed(
                            title=f'A word has been highlighted!',
                            description=message.content.replace(c[1], f'**{c[1]}**'),
                            color=discord.Color.main)
                        embed.add_field(name='Jump URL', value=message.jump_url)
                        embed.set_footer(
                            text=f'Msg sent by {message.author}',
                            icon_url=message.author.avatar_url_as(
                                static_format='png'))
                        embed.timestamp = message.created_at
                        if (
                            alerted in message.guild.members and alerted.id != message.author.id and message.channel
                                .permissions_for(message.guild.get_member(alerted.id)).read_messages
                        ):
                            await alerted.send(embed=embed)
        noacc = ud.unidecode(message.content)
        f_a = me.search(noacc)
        if (
            f_a and not message.author.bot
            and (await self.bot.application_info()).owner
            in message.guild.members
            and message.author.id != 680835476034551925
                ):
            s = list(message.content)
            s.insert(f_a.end(), '**')
            s.insert(f_a.start(), '**')
            user = self.bot.get_user(680835476034551925)
            uem = discord.Embed(
                title='Potential Mention',
                description=''.join(s),
                color=discord.Color.main)
            uem.add_field(name='Message author:', value=f'{message.author}')
            uem.add_field(name='Jump Link:', value=message.jump_url)
            uem.add_field(
                name='In server:', value=f'{message.guild}', inline=True)
            await user.send(embed=uem)

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
            name='**General**',
            value=f'**Channels:** <:text_channel:687064764421373954> {len(guild.text_channels)} | <:voice_channel:687064782167212165> {len(guild.voice_channels)}\n'
            + f'**Region:** {str(guild.region).title()}\n'
            + f'**Verification Level:** {str(guild.verification_level).capitalize()}\n'

            + f'**Emojis:** {len([emoji for emoji in guild.emojis if not emoji.animated])}/{guild.emoji_limit}\n'

            + f'**Max Upload:** {round(guild.filesize_limit * 0.00000095367432)}MB',
            inline=False)
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

    # Print to console upon disconnect - doesn't proc often
    @commands.Cog.listener()
    async def on_disconnect(self):
        print('{0.user} has disconnected from Discord\n---'.format(self.bot))


def setup(bot):
    bot.add_cog(Listeners(bot))
