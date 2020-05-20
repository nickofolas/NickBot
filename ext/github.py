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
import textwrap

import discord
from discord.ext import commands

from utils.formatters import prettify_text


class GHUser:
    def __init__(self, data):
        self.data = data
        self.name = data.get('login')
        self.url = data.get('html_url')
        self.created = data.get('created_at')
        self.bio = data.get('bio')
        self.av_url = data.get('avatar_url', 'https://i.imgur.com/OTc2e9R.png')
        self.location = data.get('location')
        self.user_id = data.get('id')

    @property
    def refol(self):
        points = {}
        [points.update({k: v}) for k, v in self.data.items() if k in
         ('public_repos', 'public_gists', 'followers', 'following')]
        return points


class Github(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='user')
    async def git_user(self, ctx, *, name):
        async with self.bot.session.get(f'https://api.github.com/users/{name}') as resp:
            json = await resp.json()
        user = GHUser(json)
        embed = discord.Embed(title=f'{user.name} ({user.user_id})',
                              description=textwrap.fill(user.bio, width=40), color=discord.Color.main) \
            .set_thumbnail(url=user.av_url)
        embed.add_field(name='Info', value='\n'.join(f"**{prettify_text(k)}** {v}" for k, v in user.refol))
        await ctx.send(embed=embed)


def setup(bot):
    for command in Github(bot).__cog_commands__:
        bot.get_command('git_group').add_command(command)
