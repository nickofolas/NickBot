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
import io
import itertools
import re
import textwrap
from datetime import datetime
from typing import Union

import discord
import humanize
from discord.ext import commands

import utils.formatters
from utils.config import conf
from utils.flags import Flags
from utils.converters import BetterUserConverter

badges = {
    'discord_employee': '<:staff:699986149288181780>',
    'discord_partner': '<:partner:699986175020105888>',
    'hs_events': '<:events:699986130761941042>',
    'hs_balance': '<:balance:699986054022824058>',
    'hs_bravery': '<:bravery:699986078307844168>',
    'hs_brilliance': '<:brilliance:699986064164782142>',
    'bug_hunter_lvl1': '<:bug1:699986089053651196>',
    'bug_hunter_lvl2': '<:bug2:699986097694048327>',
    'verified_dev': '<:dev:699988960180568135>',
    'early_supporter': '<:early:699986111975391302>'
}

activity_type_mapping = {
    discord.ActivityType.watching: 'Watching',
    discord.ActivityType.playing: 'Playing',
    discord.ActivityType.streaming: 'Streaming',
    discord.ActivityType.listening: 'Listening to'
}


class UserInfo:
    def __init__(self, user, ctx, flags):
        self.user = user
        self.context = ctx
        self.flags = flags

    @property
    def is_nitro(self):
        if self.user.is_avatar_animated():
            return True
        elif self.context.guild and isinstance(self.user, discord.Member):
            if self.user.premium_since:
                return True
        return False

    @property
    def join_pos(self):
        if self.context.guild and isinstance(self.user, discord.Member):
            return f'{sorted(self.context.guild.members, key=lambda m: m.joined_at).index(self.user) + 1:,}'
        return None

    @property
    def user_status(self):
        if not isinstance(self.user, discord.Member):
            return None
        status_icon = conf['emoji_dict'][str(self.user.status)]
        multi_status = [
            e[0] for e in [
                ('Mobile', self.user.mobile_status),
                ('Desktop', self.user.desktop_status),
                ('Web', self.user.web_status)] if str(e[1]) != 'offline']
        status_display = f"{status_icon} " \
                         f"{str(self.user.status).title().replace('Dnd', 'DND')}" \
                         f" {('(' + ', '.join(multi_status) + ')' if multi_status else '')}"
        return status_display

    @property
    async def user_activities(self):
        if not isinstance(self.user, discord.Member):
            return
        for a in self.user.activities:
            if isinstance(a, discord.Spotify):
                activity = 'Listening to **Spotify**'
            elif isinstance(a, discord.CustomActivity):
                emoji = ''
                try:
                    if a.emoji:
                        emoji = await commands.EmojiConverter().convert(
                            self.context,
                            a.emoji.id) if a.emoji.is_custom_emoji() else a.emoji
                except commands.errors.BadArgument:
                    emoji = ':question:'
                activity = f'{emoji} {a.name or ""}'
            elif isinstance(a, discord.Game):
                activity = f'Playing **{a.name}**'
            elif isinstance(a, discord.Streaming):
                activity = f'Streaming **{a.name}**'
            elif isinstance(a, discord.activity.Activity):
                activity = f'{activity_type_mapping.get(a.type)} **{a.name}**'
            # noinspection PyUnboundLocalVariable
            yield activity

    @property
    def tagline(self):
        tagline = f'{self.user} '
        if self.user.bot:
            tagline += '<:verified1:704885163003478069><:verified2:704885180162244749> ' if 'verified_bot' in \
                self.flags else '<:bot:699991045886312488> '
        if self.context.guild and isinstance(self.user, discord.Member):
            if self.user == self.context.guild.owner:
                tagline += '<:serverowner:706224911500181546> '
            if self.user.premium_since:
                tagline += '<:booster:705917670691700776> '
        if 'system' in self.flags:
            tagline += f'<:system1:706565390712701019><:system2:706565410463678485> '
        return tagline


# noinspection SpellCheckingInspection
class Info(commands.Cog):
    """Informational commands category"""

    def __init__(self, bot):
        self.bot = bot

    @commands.group(aliases=['ui'], invoke_without_command=True)
    async def userinfo(self, ctx, *, target=None):
        """Get information about the targeted user"""
        target = await BetterUserConverter().convert(ctx, target)
        user = target.obj
        flags = Flags(target.http_dict['public_flags']).flags
        user_info = UserInfo(user, ctx, flags)
        badge_list = list()
        try:
            bio = (await self.bot.conn.fetch('SELECT user_bio FROM user_data WHERE user_id=$1', user.id))[0][
                'user_bio']
        except IndexError:
            bio = None
        for i in badges.keys():
            if i in flags:
                badge_list.append(badges[i])
        badge_list = ' '.join(badge_list)
        guild_level_stats = f"**Joined Guild **" \
                            f"{humanize.naturaltime(datetime.utcnow() - user.joined_at)}" \
                            f"\n**Join Position **{user_info.join_pos}" \
            if isinstance(user, discord.Member) and ctx.guild else ''
        embed = discord.Embed(
            title=user_info.tagline,
            colour=discord.Color.main).set_thumbnail(url=user.avatar_url_as(static_format='png').__str__())
        status_display = user_info.user_status or ''
        embed.description = textwrap.dedent(f"""
        {status_display}
        {badge_list or ''}{' <:nitro:707724974248427642>' if user_info.is_nitro else ''}
        """)
        stats_disp = str()
        stats_disp += f'**Registered **{humanize.naturaltime(datetime.utcnow() - user.created_at)}'
        stats_disp += f'\n{guild_level_stats}' if guild_level_stats else ''
        embed.add_field(name='Stats', value=stats_disp)
        if acts := [a async for a in user_info.user_activities]:
            embed.add_field(
                name='Activities',
                value='\n'.join(acts),
                inline=False
            )
        if bio:
            embed.add_field(name='User Bio', value=bio[:1024], inline=False)
        await ctx.send(embed=embed)

    @userinfo.command()
    async def bio(self, ctx, *, message=None):
        """Set or remove your user bio (appears in userinfo card)
        Pass no arguments to remove your current user bio"""
        if message:
            message = re.sub(re.compile(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*(),]|(?:%['
                                        r'0-9a-fA-F][0-9a-fA-F]))+'), 'omitted', message)
        await self.bot.conn.execute('UPDATE user_data SET user_bio=$1 WHERE user_id=$2', message, ctx.author.id)
        await ctx.message.add_reaction(ctx.tick(True))

    @userinfo.command()
    @commands.guild_only()
    async def perms(self, ctx, target: discord.Member = None):
        """Show the allowed and denied permissions for a user"""
        target = target or ctx.author
        embed = discord.Embed(color=discord.Color.main)
        ls = sorted(
            [p for p in ctx.channel.permissions_for(target)],
            key=lambda x: x[1],
            reverse=True)
        for key, group in itertools.groupby(ls, lambda x: x[1]):
            joined = '\n'.join(
                [f'{ctx.tick(g[1])} {discord.utils.escape_markdown(g[0])}'
                 for g in group if
                 g[0] in [a[0] for a in filter(lambda p: p[1] is True, discord.Permissions(2080898303))]])
            embed.add_field(name='_ _', value=joined or '_ _')
        embed.set_field_at(0, name=ctx.channel.permissions_for(ctx.author).value, value=embed.fields[0].value)
        embed.set_author(
            name=target.display_name,
            icon_url=target.avatar_url_as(static_format='png'))
        await ctx.send(embed=embed)

    @userinfo.command(aliases=['spot'])
    @commands.guild_only()
    async def spotify(self, ctx, target: discord.Member = None):
        """Get info about someone's Spotify status, if they have one"""
        target = target or ctx.author
        for activity in target.activities:
            if isinstance(activity, discord.Spotify):
                ac = activity
                val = (datetime.utcnow() - ac.start)
                g = ac.duration
                e = discord.Embed(color=0x1db954)
                e.set_author(
                    name=target.display_name,
                    icon_url='https://apkwind.com/wp-content/uploads'
                             '/2019/10/spotify-1320568267425052388.png')
                e.set_thumbnail(url=ac.album_cover_url)
                e.add_field(
                    name='**Song Title**',
                    value=f'[{discord.utils.escape_markdown(ac.title)}](https://open.spotify.com/track/{ac.track_id})')
                e.add_field(
                    name='**Song Artist(s)**',
                    value=', '.join(ac.artists))
                e.add_field(name='**Album Name**', value=discord.utils.escape_markdown(ac.album))
                bar = utils.formatters.bar_make(
                    val.seconds, g.seconds, fill='◉', empty='─', point=True, length=5) if ctx.author.is_on_mobile() \
                    else utils.formatters.bar_make(
                    val.seconds, g.seconds, fill='◉', empty='─', point=True, length=25)
                e.add_field(
                    name='**Song Progress**',
                    value=f'`{(val.seconds // 60) % 60:>02}:{val.seconds % 60:>02}` '
                          + bar
                          + f' `{(g.seconds // 60) % 60:>02}:'
                            f'{g.seconds % 60:>02}`', inline=False)
                return await ctx.send(embed=e)
        else:
            await ctx.send("A Spotify status couldn't be detected!")

    @commands.group(
        aliases=['guild', 'guildinfo', 'server'],
        invoke_without_command=True)
    @commands.guild_only()
    async def serverinfo(self, ctx, guild: int = None):
        """Get info about the current server"""
        guild = self.bot.get_guild(guild) or ctx.guild
        embed = discord.Embed(
            color=discord.Color.main).set_footer(
            text=f'Created '
                 f'{humanize.naturaltime(datetime.utcnow() - guild.created_at)} | Owner: {guild.owner}')
        embed.set_author(
            name=f'{guild.name} | {guild.id}',
            icon_url=guild.icon_url_as(static_format='png'), url=guild.icon_url_as(static_format='png'))
        stats_val = f'**Channels** <:text_channel:687064764421373954> {len(guild.text_channels)} | <:voice_channel' \
                    f':687064782167212165> {len(guild.voice_channels)}\n'
        stats_val += f'**Region** {str(guild.region).title()}\n'
        stats_val += f'**Verification Level** {str(guild.verification_level).capitalize()}\n'
        stats_val += f'**Emojis** {len([emoji for emoji in guild.emojis if not emoji.animated])}/{guild.emoji_limit}\n'
        stats_val += f'**Max Upload** {round(guild.filesize_limit * 0.00000095367432)}MB'
        embed.add_field(
            name='**General**',
            value=stats_val,
            inline=True)
        statuses = {v: 0 for v in conf['emoji_dict'].values()}
        ls = sorted([m.status for m in guild.members])
        for key, group in itertools.groupby(ls, lambda x: x):
            statuses[conf['emoji_dict'][str(key)]] = len(list(group))
        s_members = [f'{k}{v:,}' for k, v in statuses.items()]
        s_members.append(f'<:bot:699991045886312488>{sum(m.bot for m in guild.members):,}')
        stat_disp = '\n'.join(s_members)
        embed.add_field(
            name=f'**Members ({len(guild.members):,})**',
            value=stat_disp,
            inline=True)
        await ctx.send(embed=embed)

    @serverinfo.command()
    @commands.guild_only()
    async def pie(self, ctx, guild: int = None):
        guild = self.bot.get_guild(guild) or ctx.guild
        async with ctx.loading(tick=False):
            await ctx.send(
                file=discord.File(
                    io.BytesIO(await self.bot.loop.run_in_executor(
                        None,
                        utils.formatters.StatusChart(
                            guild,
                            ['Online', 'DND', 'Offline', 'Idle'],
                            [utils.formatters.gen(guild, i) for i in [
                                'online', 'dnd', 'offline', 'idle']],
                            ['#43b581', '#f04847', 'grey', '#f9a61a']).make_pie)),
                    filename='test.png'))

    @serverinfo.command()
    @commands.guild_only()
    async def channels(self, ctx, guild: int = None):
        guild = self.bot.get_guild(guild) or ctx.guild
        final = list()
        for cat, chanlist in guild.by_category():
            to_append = (
                f'<:expanded:702065051036680232> {cat.name}',
                [ctx.tab(5) + (
                    ('<:text_channel:687064764421373954> ' + chan.name if not
                        chan.overwrites_for(guild.default_role).read_messages
                        is False else '<:text_locked:697526634848452639> ' + chan.name)
                    if isinstance(chan, discord.TextChannel)
                    else (
                        '<:voice_channel:687064782167212165> '
                        + chan.name if not
                        chan.overwrites_for(guild.default_role)
                            .read_messages is False else
                        '<:voice_locked:697526650333691986> ' + chan.name))
                 for chan in chanlist])
            if to_append[1]:
                final.append(to_append)
        embed = discord.Embed(color=discord.Color.main)
        for item in final:
            embed.add_field(
                name=item[0], value='\n'.join(item[1]),
                inline=False)
        await ctx.send(embed=embed)

    @serverinfo.command()
    @commands.guild_only()
    async def roles(self, ctx):
        """Returns a list of all roles in the guild"""
        await ctx.quick_menu(list(reversed([r.mention for r in ctx.guild.roles[1:]])), 20, delete_message_after=True)


def setup(bot):
    bot.add_cog(Info(bot))
