from datetime import datetime
import io
from typing import Union
import itertools

import discord
from discord.ext import commands
import humanize
import aiosqlite as asq

from utils.config import conf
import utils.data_vis
from utils.flags import UserFlags

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

perm_dict = {
    "True": '<:c_:703740667926675536>',
    "False": '<:x_:703739402094117004>'
}


def member_info(self, ctx, target, act, e):
    multi_status = [
        e[0] for e in [
            ('Mobile', target.mobile_status),
            ('Desktop', target.desktop_status),
            ('Web', target.web_status)] if str(e[1]) != 'offline']
    status_display = f"{conf['emoji_dict'][str(target.status)]} " \
        f"{str(target.status).title().replace('Dnd', 'DND')}"\
        f" {('(' + ', '.join(multi_status) + ')' if multi_status else '')}"
    for a in target.activities:
        if isinstance(a, discord.Spotify):
            act.append('Listening to **Spotify**')
        elif isinstance(a, discord.CustomActivity):
            act.append(str(a))
        elif isinstance(a, discord.Game):
            act.append(f'Playing **{a.name}**')
        elif isinstance(a, discord.activity.Activity):
            if a.type == discord.ActivityType.watching:
                act.append(f'Watching **{a.name}**')
            if a.type == discord.ActivityType.playing:
                act.append(f'Playing **{a.name}**')
            if a.type == discord.ActivityType.streaming:
                act.append(f'Streaming **{a.name}**')
            if a.type == discord.ActivityType.listening:
                act.append(f'Listening to **{a.name}**')
    acts = '\n'.join(act)
    for m in ctx.guild.members:
        e.append(m)
    e.sort(key=lambda r: r.joined_at)
    for count, val in enumerate(e, 1):
        if val == target:
            join_pos = f'{count:,}'
    return status_display, acts, act, join_pos


class Info(commands.Cog):
    """Informational commands category"""

    def __init__(self, bot):
        self.bot = bot

    @commands.group(aliases=['ui'], invoke_without_command=True)
    async def userinfo(self, ctx, *, target: Union[
            discord.Member, discord.User, int] = None):
        """Get information about the targeted user"""
        target = (await self.bot.fetch_user(target)) if \
            isinstance(target, int) else target or ctx.author
        if target != self.bot.user:
            shared = len(
                [g for g in self.bot.guilds
                    if target in g.members]
                )
            shared_display = \
                f'**Shared w/ Bot **{str(shared)} guilds' \
                if shared else ''
        else:
            shared_display = ''
        act, e, status_display, badge_list, join_pos = ([], [], None, [], None)
        if isinstance(target, discord.Member) and ctx.guild:
            status_display, acts, act, join_pos = \
                member_info(self, ctx, target, act, e)
        async with asq.connect('./database.db') as db:
            bio_get = await db.execute(
                "SELECT user_bio FROM user_data WHERE user_id=$1", (target.id,)
                )
            try:
                bio = (await bio_get.fetchone())[0]
            except Exception:
                bio = None
        flag_vals = UserFlags(
            (await self.bot.http.get_user(target.id))['public_flags'])
        for i in badges.keys():
            if i in [
                    f for f in flag_vals]:
                badge_list.append(badges[i])
        badge_list = ' '.join(badge_list)
        guild_level_stats = f"**Joined Guild **" \
            f"{humanize.naturaltime(datetime.utcnow() - target.joined_at)}"\
            f"\n**Join Position **{join_pos}\n" \
            if isinstance(target, discord.Member) and ctx.guild else ''
        embed = discord.Embed(
            title=f"{target}"
            f" {('<:bot:699991045886312488>' if target.bot else '')}",
            colour=discord.Color.main)
        embed.set_thumbnail(url=target.avatar_url_as(static_format='png'))
        status_display = status_display or ''
        embed.description = f"""
{status_display}
{badge_list or ''}
            """
        # **Shared w/ Bot **{str(shared)} guilds
        embed.add_field(
            name='Stats',
            value=f"""
**Registered **{humanize.naturaltime(datetime.utcnow() - target.created_at)}
{guild_level_stats}{shared_display}
            """,
            inline=True
            )
        if act:
            embed.add_field(
                name='Activities',
                value=acts or '',
                inline=False
            )
        if bio:
            embed.add_field(name='User Bio', value=bio[:1024], inline=False)
        await ctx.send(embed=embed)

    @userinfo.command()
    async def bio(self, ctx, *, message=None):
        async with asq.connect('./database.db') as db:
            await db.execute(
                'UPDATE user_data SET user_bio=$1 WHERE user_id=$2',
                (message, ctx.author.id))
            await db.commit()
            await ctx.message.add_reaction(ctx.tick(True))

    @userinfo.command()
    @commands.guild_only()
    async def perms(self, ctx, target: discord.Member = None):
        """Show the allowed and denied permissions for a user"""
        if target is None:
            target = ctx.author
        embed = discord.Embed(color=discord.Color.main)
        ls = sorted(
            [p for p in ctx.channel.permissions_for(target)],
            key=lambda x: x[1],
            reverse=True)
        for key, group in itertools.groupby(ls, lambda x: x[1]):
            joined = '\n'.join(
                [f'{ctx.tick(g[1])} {discord.utils.escape_markdown(g[0])}'
                 for g in group if g[0] not in conf['bad_perms']])
            embed.add_field(name='_ _', value=joined or '_ _')
        embed.set_author(
            name=target.display_name,
            icon_url=target.avatar_url_as(static_format='png'))
        embed.set_footer(text=f'{ctx.author.name}')
        embed.timestamp = ctx.message.created_at
        await ctx.send(embed=embed)

    @userinfo.command(aliases=['spot'])
    @commands.guild_only()
    async def spotify(self, ctx, target: discord.Member = None):
        """Get info about someone's Spotify status, if they have one"""
        if not target:
            target = ctx.author
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
                    value=f'[{ac.title}](https://open.s'
                    f'potify.com/track/{ac.track_id})')
                e.add_field(
                    name='**Song Artist(s)**',
                    value=', '.join(ac.artists))
                e.add_field(name='**Album Name**', value=ac.album)
                bar = utils.data_vis.bar_make(
                    val.seconds, g.seconds, '◉', '─', True, 5) if ctx.author.is_on_mobile() else utils.data_vis.bar_make(
                        val.seconds, g.seconds, '◉', '─', True, 25)
                e.add_field(
                    name='**Song Progress**',
                    value=f'`{(val.seconds//60)%60:>02}:{val.seconds%60:>02}` '
                    + bar
                    + f' `{((g.seconds)//60)%60:>02}:'
                    f'{(g.seconds)%60:>02}`', inline=False)
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
        feats = str(', '.join(guild.features)).replace('_', ' ').title()
        ctx_roles = list(itertools.islice((
            r for r in reversed(guild.roles) if '@everyone' != r.name
            ), 10)) if guild == ctx.guild else None
        admins = [
            m for m in guild.members if m.guild_permissions.administrator]
        embed = discord.Embed(
            title=' ',
            description=f'**{guild.name} | {guild.id}**',
            color=discord.Color.main).set_footer(
                text=f'Created '
                f'{humanize.naturaltime(datetime.utcnow() - guild.created_at)}')
        embed.set_thumbnail(url=guild.icon_url_as(static_format='png'))
        embed.add_field(
            name='**General**',
            value=f"""
**Channels** <:text_channel:687064764421373954> {len(guild.text_channels)} | <:voice_channel:687064782167212165> {len(guild.voice_channels)}
**Region** {str(guild.region).title()}
**Verification Level** {str(guild.verification_level).capitalize()}
**Features** {feats}
**Emojis** {len([emoji for emoji in guild.emojis if not emoji.animated])}/{guild.emoji_limit}
**Max Upload** {round(guild.filesize_limit * 0.00000095367432)}MB
            """,
            inline=True)
        statuses = {v: 0 for v in conf['emoji_dict'].values()}
        ls = sorted([m.status for m in guild.members])
        for key, group in itertools.groupby(ls, lambda x: x):
            statuses[conf['emoji_dict'][str(key)]] = len(list(group))
        stat_disp = ' '.join([f'{k}{v:,}' for k, v in statuses.items()])
        embed.add_field(
            name='**Members**',
            value=stat_disp + f"""
**Total** {len(guild.members):,}
**Admins** {len(admins)}
**Owner ** {guild.owner.name}
**Boosts **{guild.premium_subscription_count}
{utils.data_vis.bar_make(guild.premium_subscription_count, 30, '<:nitrobar_filled:698019974832324608>', '<:nitrobar_empty:698019957983674459>', False, 5)}
            """,
            inline=True)
        if ctx_roles:
            embed.add_field(
                name=f'**Top 10 Roles ({len(guild.roles)} total)**',
                value=''.join([rt.mention for rt in ctx_roles]),
                inline=False)
        await ctx.send(embed=embed)

    @serverinfo.command()
    @commands.guild_only()
    async def pie(self, ctx, guild: int = None):
        guild = self.bot.get_guild(guild) or ctx.guild
        await ctx.send(
            file=discord.File(
                io.BytesIO(await self.bot.loop.run_in_executor(
                    None,
                    utils.data_vis.StatusChart(
                        guild,
                        ['Online', 'DND', 'Offline', 'Idle'],
                        [utils.data_vis.gen(guild, i) for i in [
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
                        is False else '<:text_locked:697526634848452639> '
                        + chan.name) if isinstance(chan, discord.TextChannel)
                    else (
                        '<:voice_channel:687064782167212165> '
                        + chan.name if not
                        chan.overwrites_for(guild.default_role)
                        .read_messages is False else
                        '<:voice_locked:697526650333691986> ' + chan.name))
                    for chan in chanlist if chan.permissions_for(ctx.author)
                    .read_messages is True])
            if to_append[1]:
                final.append(to_append)
        embed = discord.Embed(color=discord.Color.main)
        for item in final:
            embed.add_field(
                name=item[0], value='\n'.join(item[1]),
                inline=False)
        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Info(bot))
