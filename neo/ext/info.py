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
from collections import Counter, namedtuple, deque

import discord
import humanize
from discord.ext import commands
from dateutil.relativedelta import relativedelta

import neo
import neo.utils.formatters
from neo.utils.converters import BetterUserConverter

activity_type_mapping = {
    discord.ActivityType.watching: 'Watching',
    discord.ActivityType.playing: 'Playing',
    discord.ActivityType.streaming: 'Streaming',
    discord.ActivityType.listening: 'Listening to'
}

def to_elapsed(time):
    return f'{(time.seconds // 60) % 60:>02}:{time.seconds % 60:>02}'

statuses_base = namedtuple('statuses_base', 'online dnd idle offline', defaults=(0, 0, 0, 0))
info_emojis = neo.conf['emojis']['infos']

class UserInfo:
    __slots__ = ('user', 'ctx', 'flags')

    """Wraps up a discord.Member or discord.User's user info"""
    def __init__(self, user, ctx, flags):
        self.user = user
        self.ctx = ctx
        self.flags = flags

    @property
    def is_nitro(self):
        if self.user.is_avatar_animated():
            return True
        elif any(g.get_member(self.user.id).premium_since for g in self.ctx.bot.guilds if self.user in g.members):
            return True
        elif mem := discord.utils.get(self.ctx.bot.get_all_members(), id=self.user.id):
            if a := discord.utils.get(mem.activities, type=discord.ActivityType.custom):
                if a.emoji:
                    if a.emoji.is_custom_emoji():
                        return True
        return False

    @property
    def join_pos(self):
        if self.ctx.guild and isinstance(self.user, discord.Member):
            return f'{sorted(self.ctx.guild.members, key=lambda m: m.joined_at).index(self.user) + 1:,}'
        return None

    @property
    def user_status(self):
        if not isinstance(self.user, discord.Member):
            return ''
        status_icon = neo.conf['emojis']['status_emojis'][str(self.user.status)]
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
    def user_activities(self):
        if not isinstance(self.user, discord.Member):
            return
        for a in self.user.activities:
            if isinstance(a, discord.Spotify):
                activity = 'Listening to **Spotify**'
            elif isinstance(a, discord.CustomActivity):
                emoji = ''
                if a.emoji:
                    emoji = ':question:' if a.emoji.is_custom_emoji() and not self.ctx.bot.get_emoji(a.emoji.id) else a.emoji
                activity = f'{emoji} {a.name or ""}'
            elif isinstance(a, discord.Game):
                activity = f'Playing **{a.name}**'
            elif isinstance(a, discord.Streaming):
                activity = f'Streaming **{a.name}**'
            elif isinstance(a, discord.activity.Activity):
                activity = f'{activity_type_mapping.get(a.type)} **{a.name}**'
            yield activity

    @property
    def tagline(self):
        tagline = f'{self.user} '
        if self.user.bot:
            tagline += ''.join(info_emojis[f'veribot{i}'] for i in (1, 2)) if 'verified_bot' in \
                self.flags else info_emojis['bot']
        if self.ctx.guild and isinstance(self.user, discord.Member):
            if self.user == self.ctx.guild.owner:
                tagline += info_emojis['serverowner']
            if self.user.premium_since:
                tagline += info_emojis['booster']
        if 'system' in self.flags:
            tagline += ''.join(info_emojis[f'system{i}'] for i in (1, 2))
        return tagline


class Info(commands.Cog):
    """Informational commands category"""

    def __init__(self, bot):
        self.bot = bot

    @commands.group(aliases=['ui'], invoke_without_command=True)
    async def userinfo(self, ctx, *, target=None):
        """Get information about the targeted user"""
        user = await BetterUserConverter().convert(ctx, target)
        flags = [flag for flag, value in dict(user.public_flags).items() if value is True]
        user_info = UserInfo(user, ctx, flags)
        badge_list = list()
        for i in (badges := neo.conf['emojis']['badges']).keys():
            if i in flags:
                badge_list.append(badges[i])
        badge_list = ' '.join(badge_list) or ''
        guild_level_stats = f"**Joined Guild **" \
                            f"{humanize.naturaltime(datetime.utcnow() - user.joined_at)}" \
                            f"\n**Join Position **{user_info.join_pos}" \
            if isinstance(user, discord.Member) and ctx.guild else ''
        embed = neo.Embed(title=user_info.tagline)
        embed.set_thumbnail(url=user.avatar_url_as(static_format='png').__str__())
        status_display = user_info.user_status
        embed.description = textwrap.dedent(f"""
        {status_display}
        {badge_list} {info_emojis['nitro'] if user_info.is_nitro else ''}
        """)
        stats_disp = str()
        stats_disp += f'**Registered **{humanize.naturaltime(datetime.utcnow() - user.created_at)}'
        stats_disp += f'\n{guild_level_stats}' if guild_level_stats else ''
        embed.add_field(name='Stats', value=stats_disp)
        if acts := [*user_info.user_activities]:
            embed.add_field(
                name='Activities',
                value='\n'.join(acts),
                inline=False
            )
        await ctx.send(embed=embed)

    @userinfo.command()
    @commands.guild_only()
    async def perms(self, ctx, target: discord.Member = None):
        """Show the allowed and denied permissions for a user"""
        target = target or ctx.author
        embed = neo.Embed()
        ls = sorted(
            [*ctx.channel.permissions_for(target)],
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
        """Displays information about a Member's Spotify status, is they have one"""
        target = target or ctx.author
        if ac := discord.utils.find(lambda a: isinstance(a, discord.Spotify), target.activities):
            _len = 5 if ctx.author.is_on_mobile() else 17
            album = textwrap.fill(discord.utils.escape_markdown(ac.album), width=42.5)
            artist = neo.utils.formatters.pluralize('Artist', ac.artists)
            artists = textwrap.fill(', '.join(ac.artists), width=42.5)
            val = (datetime.utcnow() - ac.start)
            bar = neo.utils.formatters.bar_make(
                val.seconds, ac.duration.seconds, fill='◉', empty='─', point=True, length=_len)
            e = discord.Embed(
                color=0x1db954,
                title=f'`{to_elapsed(val)}` {bar} `{to_elapsed(ac.duration)}`',
                description=f"**Album** {album}\n**{artist}** {artists}")
            e.set_thumbnail(url=ac.album_cover_url)
            e.set_author(name=textwrap.fill(ac.title[:256], width=42.5),
                         icon_url='https://i.imgur.com/PA3vvdN.png',
                         url=f'https://open.spotify.com/track/{ac.track_id}')  # yarl maybe?
            return await ctx.send(embed=e)
        else:
            await ctx.send('Couldn\'t detect a Spotify status')

    @userinfo.command(aliases=['rpc', 'richpres'])
    @commands.guild_only()
    async def rich_presence(self, ctx, target: discord.Member = None):
        """Returns an embed mimicking a user's rich presence"""
        target = target or ctx.author
        if ac := discord.utils.find(
                lambda a: bool(a.assets) is True,
                filter(lambda a: hasattr(a, 'assets'), target.activities)):
            description = []
            for attr in (ac.details, ac.state):
                if attr: description.append(attr)
            if ac.start:
                elapsed = relativedelta(seconds=(datetime.utcnow() - ac.start).total_seconds()).normalized()
                elapsed_formatted = []
                for unit in ('days', 'hours', 'minutes', 'seconds'):
                    elapsed_formatted.append(f'{getattr(elapsed, unit):>02}')
                description.append(f"{':'.join(elapsed_formatted)} elapsed")
            embed = neo.Embed(description=discord.utils.escape_markdown('\n'.join(description)))
            embed.set_author(icon_url=ac.small_image_url or '', name=ac.name)
            embed.set_thumbnail(url=ac.large_image_url or '')
            return await ctx.send(embed=embed)
        else:
            await ctx.send('Couldn\'t find a valid rich presence')

    @commands.group(
        aliases=['guild', 'guildinfo', 'server'],
        invoke_without_command=True)
    @commands.guild_only()
    async def serverinfo(self, ctx):
        """Get info about the current server"""
        guild = ctx.guild
        embed = neo.Embed()
        embed.set_footer(
            text=f'Created '
                 f'{humanize.naturaltime(datetime.utcnow() - guild.created_at)} | Owner: {guild.owner}')
        embed.set_author(
            name=f'{guild.name} | {guild.id}',
            icon_url=guild.icon_url_as(static_format='png'), url=guild.icon_url_as(static_format='png'))
        stats_val = f'**Channels** {neo.conf["emojis"]["channel_indicators"]["TextChannel"]}' \
                    f'{len(guild.text_channels)} | {neo.conf["emojis"]["channel_indicators"]["VoiceChannel"]}' \
                    f'{len(guild.voice_channels)}\n'
        stats_val += f'**Region** {str(guild.region).title()}\n'
        stats_val += f'**Verification Level** {str(guild.verification_level).capitalize()}\n'
        stats_val += f'**Emojis** {len([emoji for emoji in guild.emojis if not emoji.animated])}/{guild.emoji_limit}\n'
        stats_val += f'**Max Upload** {round(guild.filesize_limit * 0.00000095367432)}MB'
        embed.add_field(name='**General**', value=stats_val, inline=True)
        statuses = statuses_base(**Counter([m.status.value for m in guild.members]))._asdict()
        s_members = [f'{neo.conf["emojis"]["status_emojis"][k]} {v:,}' for k, v in statuses.items()]
        s_members.append(f'{info_emojis["bot"]} {sum(m.bot for m in guild.members):,}')
        embed.add_field(
            name=f'**Members [{guild.member_count:,}]**',
            value='\n'.join(s_members),
            inline=True)
        await ctx.send(embed=embed)

    @staticmethod
    def by_category_v2(g):
        def sep_text_voice(channel_group):
            sep = deque(sorted(channel_group, key=(lambda c: c.position)))
            sep.rotate((- len([c for c in sep if isinstance(c, discord.VoiceChannel)])))
            return sep
        top_non_cat = filter(
            (lambda c: ((not c.category) and (not isinstance(c, discord.CategoryChannel)))),
            g.channels)
        (yield sep_text_voice(top_non_cat))
        for ch in sorted(g.categories, key=(lambda c: c.position)):
            (yield (ch, sep_text_voice(ch.channels)))

    @staticmethod
    def format_channels(channel):
        spacer = '\N{zwsp} _ _'
        if isinstance(channel, discord.CategoryChannel):
            return f'<:expanded:743229782090579968> **{channel.name.upper()}**'
        elif isinstance(channel, (discord.TextChannel, discord.VoiceChannel)):
            suffix = ''
            if channel.overwrites_for(channel.guild.default_role).read_messages is False:
                suffix = '-locked'
            if isinstance(channel, discord.TextChannel) and channel.is_nsfw():
                suffix = '-nsfw'
            emoji = neo.conf['emojis']['channel_indicators'][channel.__class__.__name__ + suffix]
            return f'{spacer*5} {emoji} {discord.utils.escape_markdown(channel.name)}'

    @serverinfo.command()
    @commands.guild_only()
    async def channels(self, ctx):
        """Lists out the guild's channels in an order that mirrors that of the Discord UI"""
        final = list(map(
            self.format_channels,
            neo.utils.formatters.flatten(self.by_category_v2(ctx.guild))))
        await ctx.paginate(
            neo.utils.formatters.group(final, 25),
            1, clear_reactions_after=True,
            delete_on_button=True)

    @serverinfo.command()
    @commands.guild_only()
    async def roles(self, ctx):
        """Returns a list of all roles in the guild"""
        await ctx.paginate(list(reversed([r.mention for r in ctx.guild.roles[1:]])), 20, delete_message_after=True)

    @commands.command(name='resolve')
    async def _resolve_invite(self, ctx, *, guild_invite):
        """Resolves information from a guild invite code/URL"""
        async with ctx.loading():
            guild = (invite := await self.bot.fetch_invite(guild_invite)).guild
            features_pprint = ', '.join(
                map(neo.utils.formatters.prettify_text, guild.features or ['None'])).title().replace('Url', 'URL')
            online = invite.approximate_presence_count
            total = invite.approximate_member_count
            desc = f"**{online:,} [{online/total * 100:.0f}%] of {total:,} members online**"
            if guild.description:
                desc += f"\n{textwrap.fill(guild.description, width=45)}"
            embed = neo.Embed(description=desc, title=guild.name)
            embed.set_thumbnail(url=guild.icon_url_as(static_format='png'))
            embed.set_footer(text=f'Created {humanize.naturaltime(guild.created_at)} | ID: {guild.id}')
            other_ = f"**Invite URL** {invite}"
            other_ += f'\n**Verification Level** {str(guild.verification_level).title()}'
            other_ += f"\n**Features** {textwrap.fill(features_pprint, width=45)}" 
            embed.add_field(name='Info', value=other_)
            await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Info(bot))
