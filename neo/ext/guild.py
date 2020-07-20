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

from neo.utils.checks import is_owner_or_administrator
from neo.utils.converters import BoolConverter
from neo.utils.formatters import prettify_text

custom_emoji = re.compile(
    r'(<a?:\w*:\d*>)|([\U00002600-\U000027BF])|([\U0001f300-\U0001f64F])|([\U0001f680-\U0001f6FF])')


class Guild(commands.Cog):
    """Everything to do with guild management can be found here"""

    def __init__(self, bot):
        self.bot = bot

    def cog_check(self, ctx):
        return bool(ctx.guild)

    @flags.add_flag('search_depth', type=int, nargs='?', default=5)
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
    @has_permissions(manage_messages=True)
    @commands.max_concurrency(1, commands.BucketType.channel)
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
        user_obj = await self.bot.fetch_user(member) if isinstance(member, int) else member
        await ctx.guild.ban(user_obj, reason=f'{ctx.author} ({ctx.author.id}) - {reason}')
        await ctx.send(f'Banned **{user_obj}**')

    @commands.command()
    @has_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member, *, reason=None):
        """Kick a member - optional reason can be provided"""
        await member.kick(reason=f'{ctx.author} ({ctx.author.id}) - {reason}')
        await ctx.send(f'Kicked **{member}**')

def setup(bot):
    bot.add_cog(Guild(bot))
