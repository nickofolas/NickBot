from typing import Union

import discord
from discord.ext import commands


def is_owner_or_administrator():
    async def predicate(ctx):
        is_owner = await ctx.bot.is_owner(ctx.author)
        return is_owner or ctx.channel.permissions_for(ctx.author).administrator
    return commands.check(predicate)


def exclude_channels(id: Union[list, int]):
    def predicate(ctx):
        if isinstance(id, int):
            return ctx.channel.id != id
        else:
            return ctx.channel.id not in id
    return commands.check(predicate)
