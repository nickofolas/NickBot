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

import neo
from neo.utils.checks import is_owner_or_administrator

class Starboard(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_check(self, ctx):
        if not self.bot.guild_cache[ctx.guild.id]['starboard']:
            raise commands.CommandError('Starboard is not enabled in this guild')
        return await self.bot.is_owner(ctx.author)

    @commands.group(name='starboard', invoke_without_command=True)
    @is_owner_or_administrator()
    async def starboard_config(self, ctx):
        _config = self.bot.guild_cache[ctx.guild.id]
        if _config['starboard'] is False:
            raise commands.CommandError(
                'Starboard has not been enabled for this guild yet')
        if (ch := _config.get('starboard_channel_id')) is not None:
            star_channel = ctx.guild.get_channel(ch).mention
        else:
            star_channel = 'Not configured'
        description = f'**Starboard Channel** {star_channel}'
        description += '\n**Star Requirement** {}'.format(_config['starboard_star_requirement'])
        embed = neo.Embed(title=f'{ctx.guild}\'s starboard settings',
                          description=description)
        await ctx.send(embed=embed)

def setup(bot):
    bot.add_cog(Starboard(bot))
