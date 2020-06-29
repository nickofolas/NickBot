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
from collections import namedtuple
from contextlib import suppress
import re

# noinspection PyPackageRequirements
from discord.ext import commands
import discord

BetterUser = namedtuple('BetterUser', 'obj')
RedditMatch = namedtuple('RedditMatch', 'name id match')
u_conv = commands.UserConverter()
m_conv = commands.MemberConverter()

reddit_url = re.compile(r"^((https://)?(www\.|old\.|new\.)?reddit.com)?/?(?P<type>user|u|r)?/?(?P<name>[\w\-]*)(/comments/(?P<id>[\w\-\_]*))?/?")
github_pattern = re.compile(r"^((https://)?(www\.)?github.com)?/?(?P<user>[\w\.\-]*)/?(?P<repo>[\w\-\.]*)?/?")


class BoolConverter(commands.Converter):
    async def convert(self, ctx, argument):
        true_values = ['on', 'yes', 'true', 'y', '1']
        false_values = ['off', 'no', 'false', 'n', '0']
        if argument.lower() in true_values:
            return True
        elif argument.lower() in false_values:
            return False
        else:
            raise commands.BadArgument('Input could not be converted into a true or false result')

class BetterUserConverter(commands.Converter):
    async def convert(self, ctx, argument):
        out = ctx.author if not argument else None
        for converter in (m_conv, u_conv):
            if out:
                break
            with suppress(Exception):
                out = await converter.convert(ctx, argument)
        if out is None:
            try:
                out = await ctx.bot.fetch_user(argument)
            except discord.HTTPException:
                raise commands.CommandError("Invalid user provided")
        return BetterUser(obj=out)


class CBStripConverter(commands.Converter):
    async def convert(self, ctx, argument) -> str:
        if argument.startswith('```') and argument.endswith('```'):
            return '\n'.join(argument.split('\n')[1:-1])

            # remove `foo`
        return argument.strip('` \n')


class RedditConverter(commands.Converter):
    async def convert(self, ctx, argument):
        if match := re.match(reddit_url, argument.strip('<>')):
            return RedditMatch(match.groupdict().get('name'), match.groupdict().get('id'), match)
        raise commands.CommandError(f"Invalid argument '{argument}'")


class GitHubConverter(commands.Converter):
    async def convert(self, ctx, argument):
        return github_pattern.search(argument.strip('<>')).groupdict()
