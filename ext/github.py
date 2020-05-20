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
from datetime import datetime

import discord
from discord.ext import commands
from humanize import naturaltime as nt

from utils.formatters import prettify_text


class GHUser:
    def __init__(self, data):
        self.data = data
        self.name = data.get('login')
        self.url = data.get('html_url')
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

    @property
    def created(self):
        str_time = self.data.get('created_at')
        return datetime.strptime(str_time, "%Y-%m-%dT%H:%M:%SZ")


# noinspection PyMethodParameters,PyUnresolvedReferences
class Github(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def cog_unload(self):
        [self.bot.remove_command(command.name) for command in self.get_commands()]

    @commands.command(name='user')
    async def git_user(ctx, *, name):
        async with ctx.bot.session.get(f'https://api.github.com/users/{name}') as resp:
            json = await resp.json()
        user = GHUser(json)
        embed = discord.Embed(title=f'{user.name} ({user.user_id})',
                              description=textwrap.fill(user.bio, width=40), url=user.url, color=discord.Color.main) \
            .set_thumbnail(url=user.av_url)
        embed.add_field(name='Info', value='\n'.join(f"**{prettify_text(k)}** {v}" for k, v in user.refol.items()))
        embed.set_footer(text=f'Created {nt(datetime.utcnow() - user.created)}')
        await ctx.send(embed=embed)


def setup(bot):
    for command in Github(bot).get_commands():
        bot.get_command('github').remove_command(command.name)
        bot.get_command('github').add_command(command)
