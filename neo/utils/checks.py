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
import discord
from discord.ext import commands


def is_owner_or_administrator():
    async def predicate(ctx):
        is_owner = await ctx.bot.is_owner(ctx.author)
        allowed = is_owner or ctx.channel.permissions_for(ctx.author).administrator
        if not allowed:
            raise commands.CheckFailure(
                'This command can only be used by guild admins and neo developers')
        return True

    return commands.check(predicate)


def exclude_channels(guild_id):
    def predicate(ctx):
        if isinstance(guild_id, int):
            return ctx.channel.id != guild_id
        else:
            return ctx.channel.id not in guild_id

    return commands.check(predicate)


def snipe_check():
    def predicate(ctx):
        if ctx.bot.guild_cache[ctx.guild.id].get('snipes', False) is False:
            raise commands.CommandError(
                'This command is opt-in, and your guild admins'
                ' have not yet enabled it via guild config')
        return True

    return commands.check(predicate)

