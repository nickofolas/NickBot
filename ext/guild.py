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
import argparse
import re
import shlex
from typing import Union
from types import SimpleNamespace
from contextlib import suppress

import discord
from discord.ext import commands, flags
from discord.ext.commands import has_permissions

from utils.checks import is_owner_or_administrator
from utils.converters import BoolConverter
from utils.formatters import prettify_text

custom_emoji = re.compile(
    r'(<a?:\w*:\d*>)|([\U00002600-\U000027BF])|([\U0001f300-\U0001f64F])|([\U0001f680-\U0001f6FF])')


class Guild(commands.Cog):
    """Everything to do with guild management can be found here"""

    def __init__(self, bot):
        self.bot = bot

    def cog_check(self, ctx):
        if ctx.guild:
            return True
        else:
            return False

    @flags.add_flag('-u', '--user', nargs='+')
    @flags.add_flag('-c', '--contains', nargs='+')
    @flags.add_flag('-o', '--or', action='store_true', dest='_or')
    @flags.add_flag('-n', '--not', action='store_true', dest='_not')
    @flags.add_flag('-e', '--emoji', action='store_true')
    @flags.add_flag('-b', '--bot', action='store_const', const=lambda m: m.author.bot)
    @flags.add_flag(
        '-f', '--files',
        action='store_const',
        const=lambda m: len(m.attachments))
    @flags.add_flag(
        '-r', '--reactions',
        action='store_const',
        const=lambda m: len(m.reactions))
    @flags.add_flag('search_depth', type=int, nargs='?', default=5)
    @has_permissions(manage_messages=True)
    @flags.command(name='clear', aliases=['c'])
    async def custom(self, ctx, **args):
        """Clear messages from the channel
        Can be specialised using flags"""
        args = SimpleNamespace(**args)
        predicates = []
        [predicates.append(flag) for flag in (args.bot, args.files) if flag]
        if args.emoji:
            predicates.append(lambda m: custom_emoji.search(m.content))
        if args.user:
            users = []
            converter = commands.MemberConverter()
            for u in args.user:
                with suppress(Exception):
                    user = await converter.convert(ctx, u)
                    users.append(user)
            predicates.append(lambda m: m.author in users)
        if args.contains:
            predicates.append(
                lambda m: any(sub in m.content for sub in args.contains))
        op = all if not args._or else any

        def predicate(m):
            r = op(p(m) for p in predicates)
            if args._not:
                return not r
            return r

        args.search_depth = max(0, min(2000, args.search_depth))  # clamp from 0-2000
        async with ctx.loading():
            if args.reactions:
                [await m.clear_reactions() async for m in ctx.channel.history(limit=args.search_depth) if m.reactions]
                return
            await ctx.channel.purge(limit=args.search_depth, check=predicate, before=ctx.message)

    @commands.command()
    @has_permissions(ban_members=True)
    async def ban(self, ctx, member: Union[discord.Member, int], *, reason=None):
        """Issue a ban, can use the ID of a member outside the guild to hackban them"""
        to_ban = discord.Object(id=member) if isinstance(member, int) else member
        user_obj = await self.bot.fetch_user(member) if isinstance(member, int) else member
        await ctx.guild.ban(to_ban, reason=f'{ctx.author} ({ctx.author.id}) - {reason}')
        await ctx.send(f'Banned **{user_obj}**')

    @commands.command()
    @has_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member, *, reason=None):
        """Kick a member - optional reason can be provided"""
        await member.send(
            f'You have been kicked from the {ctx.guild} server. Reason: **{reason}**'
        )
        await member.kick(reason=reason)
        await ctx.send(f'{member} was kicked - **{reason}**')
        await ctx.message.delete()

    @commands.group(name='config', aliases=['cfg'], invoke_without_command=True)
    @is_owner_or_administrator()
    async def guild_config(self, ctx):
        """
        View or modify the configuration for the current guild.
        """
        current_settings = self.bot.guild_cache[ctx.guild.id]
        readable_settings = list()
        for k, v in current_settings.items():
            if isinstance(v, bool):
                readable_settings.append(f'**{ctx.toggle(v)} {discord.utils.escape_markdown(k)}**')
            else:
                readable_settings.append(f'**{discord.utils.escape_markdown(k)}** `{v}`')
        await ctx.send(embed=discord.Embed(
            title='Current Guild Settings', description='\n'.join(readable_settings),
            color=discord.Color.main).set_thumbnail(url=ctx.guild.icon_url_as(static_format='png')))

    @guild_config.command(aliases=['pfx'])
    @is_owner_or_administrator()
    async def prefix(self, ctx, new_prefix=None):
        """Change the prefix for the current server"""
        if new_prefix is None:
            return await ctx.send(embed=discord.Embed(
                title='Prefixes for this guild',
                description='\n'.join(
                    sorted(set([p.replace('@!', '@') for p in await self.bot.get_prefix(ctx.message)]),
                           key=lambda p: len(p))),
                color=discord.Color.main))
        await self.bot.conn.execute(
            'INSERT INTO guild_prefs (guild_id, prefix) VALUES ($1, $2) ON CONFLICT (guild_id) DO UPDATE SET prefix=$2',
            ctx.guild.id, new_prefix)
        await self.bot.guild_cache.refresh()
        await ctx.send(f'Prefix successfully changed to `{new_prefix}`')

    @guild_config.command(name='index')
    @is_owner_or_administrator()
    async def _index_emojis_toggle(self, ctx, on_off: BoolConverter):
        """
        Toggle whether or not emojis from the current guild will be indexed by emoji commands
        """
        await self.bot.conn.execute('UPDATE guild_prefs SET index_emojis=$1 WHERE guild_id=$2', on_off, ctx.guild.id)
        await self.bot.guild_cache.refresh()
        await ctx.message.add_reaction(ctx.tick(True))


def setup(bot):
    bot.add_cog(Guild(bot))
