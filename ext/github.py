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
from contextlib import suppress
from datetime import datetime

import discord
from discord.ext import commands, flags
from humanize import naturaltime as nt

from utils.formatters import prettify_text, from_tz, group
from utils.errors import ApiError
from utils.paginator import PagedEmbedMenu, CSMenu

path_mapping = {'repos': 'repositories', 'users': 'users'}


class GHUser:
    def __init__(self, data):
        self.data = data
        self.name = data.get('login')
        self.url = data.get('html_url')
        self.bio = data.get('bio')
        self.av_url = data.get('avatar_url', 'https://i.imgur.com/OTc2e9R.png')
        self.location = data.get('location')
        self.user_id = data.get('id')
        self.created = from_tz(data.get('created_at'))

    @property
    def refol(self):
        points = {}
        [points.update({k: v}) for k, v in self.data.items() if k in
         ('public_repos', 'public_gists', 'followers', 'following')]
        return points


class GHRepo:
    def __init__(self, data):
        self.data = data
        self.name = data.get('name')
        self.full_name = data.get('full_name')
        self.repo_id = data.get('id')
        self.owner = GHUser(data.get('owner'))
        self.url = data.get('html_url')
        self.description = data.get('description')
        self.created = from_tz(data.get('created_at'))
        self.last_push = from_tz(data.get('pushed_at'))
        self.gazers = data.get('stargazers_count')
        self.license_id = self.license()
        self.forks = data.get('forks')
        self.language = data.get('language')
        self.watchers = data.get('subscribers_count')

    def license(self):
        if lic := self.data.get('license'):
            return lic.get('spdx_id')
        return None


type_mapping = {'repositories': GHRepo, 'users': GHUser}


class GHListing:
    def __init__(self, data, search_type):
        self.data = data
        self.search_type = search_type
        self.total = data.get('total_count')
        self.items = data.get('items')

    def __iter__(self):
        for item in self.build_object_listing():
            yield item

    def build_object_listing(self):
        return [type_mapping[self.search_type](item) for item in self.items]

def gen_listing_embeds(listing: GHListing, search):
    for item in group(listing, 5):
        embed = discord.Embed(color=discord.Color.main).set_author(
            name=search.split('github.com')[1], icon_url="https://i.imgur.com/CpKHIaF.png")
        embed.description = '\n'.join(f'[{obj.name}]({obj.url}) - {obj.data.get("id")}' for obj in item)
        yield embed


# noinspection PyMethodParameters,PyUnresolvedReferences
class Github(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def cog_unload(self):
        [self.bot.remove_command(command.name) for command in self.get_commands()] 

    @commands.command(name='user')
    async def git_user(ctx, *, name):
        """Fetch data on a github user"""
        async with ctx.loading(tick=False), ctx.bot.session.get(f'https://api.github.com/users/{name}') as resp:
            if resp.status != 200:
                raise ApiError(f'Received {resp.status}')
            json = await resp.json()
        with suppress(UnboundLocalError):
            user = GHUser(json)
            embed = discord.Embed(title=f'{user.name} ({user.user_id})',
                                  description=textwrap.fill(user.bio, width=40) if user.bio else None, url=user.url, color=discord.Color.main) \
                .set_thumbnail(url=user.av_url)
            ftext = '\n'.join(f"**{prettify_text(k)}** {v}" for k, v in user.refol.items())
            ftext += f'\n<:locationmarker:713024424240218162> {user.location}' if user.location else ''
            embed.add_field(name='Info', value=ftext)
            embed.set_footer(text=f'Created {nt(datetime.utcnow() - user.created)}')
            await ctx.send(embed=embed)

    @commands.command(name='repo')
    async def git_repo(ctx, *, repo_path):
        """Fetch data on a github repository
        MUST be a public repository, path format is {user}/{repo name}"""
        async with ctx.loading(tick=False), ctx.bot.session.get(f'https://api.github.com/repos/{repo_path}') as resp:
            if resp.status != 200:
                raise ApiError(f'Received {resp.status}')
            json = await resp.json()
        with suppress(UnboundLocalError):
            repo = GHRepo(json)
            embed = discord.Embed(title=f'{repo.full_name} ({repo.repo_id})',
                                  description=textwrap.fill(repo.description, width=40) if repo.description else None,
                                  color=discord.Color.main, url=repo.url).set_thumbnail(url=repo.owner.av_url)
            fone_txt = str()
            fone_txt += f'**Owner** {repo.owner.name}\n'
            fone_txt += f'**Language** {repo.language}\n'
            fone_txt += f'**Forks** {repo.forks}\n'
            ftwo_txt = str()
            ftwo_txt += f':scales: {repo.license_id}\n'
            ftwo_txt += f':star: {repo.gazers}\n'
            ftwo_txt += f':telescope: {repo.watchers}'
            embed.add_field(name='Info', value=fone_txt)
            embed.add_field(name='_ _', value=ftwo_txt)
            push_delta = (datetime.utcnow() - repo.last_push)
            create_delta = (datetime.utcnow() - repo.created)
            embed.set_footer(text=f'Created {nt(create_delta)} | Last push {nt(push_delta)}')
            await ctx.send(embed=embed)

    @flags.add_flag('query', nargs='*')
    @flags.add_flag('-p', '--path', choices=['repos', 'users'], default='repos')
    @commands.cooldown(1, 5, commands.BucketType.user)
    @flags.command(name='search')
    async def git_search(ctx, **flags):
        """Make a GitHub search
        Valid paths are 'repos', 'users'"""
        async with ctx.loading(tick=False), ctx.bot.session.get(
                f'https://api.github.com/search/{path_mapping[flags.get("path")]}', params={'q': flags.get('query')[0]}) as resp:
            if resp.status != 200:
                raise ApiError(f'Received {resp.status}')
            json = await resp.json()
        with suppress(UnboundLocalError):
            try:
                listing = GHListing(json, path_mapping[flags.get("path")])
                source = PagedEmbedMenu([*gen_listing_embeds([*listing], str(resp.url))])
                menu = CSMenu(source, delete_message_after=True)
                await menu.start(ctx)
            except IndexError:
                return await ctx.send('No results')


def setup(bot):
    for command in Github(bot).get_commands():
        bot.get_command('github').remove_command(command.name)
        bot.get_command('github').add_command(command)
