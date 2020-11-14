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
from random import choice
from string import ascii_letters

import discord
import neo
from discord.ext import commands
from humanize import naturaltime as nt
from neo.models import GHRepo, GHUser
from neo.utils.converters import ArbitraryGitHubConverter, GitHubConverter
from neo.utils.errors import ApiError
from neo.utils.formatters import prettify_text
from yarl import URL

path_mapping = {"repos": "repositories"}
gh_emojis = neo.conf["emojis"]["github"]


async def user_callback(ctx, user):
    embed = neo.Embed(
        title=f"{user.name} ({user.user_id})",
        description=textwrap.fill(user.bio, width=40) if user.bio else None,
        url=str(user.url),
    ).set_thumbnail(url=user.av_url)
    ftext = "\n".join(f"**{prettify_text(k)}** {v}" for k, v in user.refol.items())
    ftext += f'\n{gh_emojis["location"]} {user.location}' if user.location else ""
    embed.add_field(name="Info", value=ftext)
    embed.set_footer(
        text=f"Created {nt(datetime.utcnow() - user.created)} | "
        f"Updated {nt(datetime.utcnow() - user.updated)}"
    )
    await ctx.send(embed=embed)


async def repo_callback(ctx, repo):
    embed = neo.Embed(
        title=f"{repo.full_name} ({repo.repo_id})",
        description=textwrap.fill(repo.description, width=40)
        if repo.description
        else None,
        url=str(repo.html_url),
    ).set_thumbnail(url=str(repo.owner.av_url))
    fone_txt = f"**Owner** {repo.owner.name}\n"
    fone_txt += f"**Language** {repo.language}\n"
    fone_txt += f"**Forks** {repo.forks:,}\n"
    fone_txt += f"**Pushed** {nt(datetime.utcnow() - repo.last_push)}"
    ftwo_txt = f'{gh_emojis["license"]} {repo.license_id}\n'
    ftwo_txt += f'{gh_emojis["star"]} {repo.gazers:,}\n'
    ftwo_txt += f'{gh_emojis["watcher"]}  {repo.watchers:,}\n'
    ftwo_txt += f"{gh_emojis['commit']} {await repo.commit_count(ctx.bot.session)}"
    embed.add_field(name="Info", value=fone_txt)
    embed.add_field(name="_ _", value=ftwo_txt)
    embed.set_footer(text=f"Created {nt(datetime.utcnow() - repo.created)}")
    await ctx.send(embed=embed)


async def delegate_callbacks(ctx, entity):
    if isinstance(entity, GHUser):
        callback = user_callback
    elif isinstance(entity, GHRepo):
        callback = repo_callback
    await callback(ctx, entity)


class Github(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="get")
    async def git_arbitrary(ctx, *, entity: ArbitraryGitHubConverter):
        """
        Fetch information on a GitHub entity using an abstract naming model.
        Available models are users and repositories.
        A repository is indicated with `<repo owner>/<repo name>` notation.
        Likewise, a user is indicated simply via `<username>` notation.
        """
        async with ctx.loading(tick=False):
            await delegate_callbacks(ctx, entity)


def setup(bot):
    for command in Github(bot).get_commands():
        bot.get_command("github").remove_command(command.name)
        bot.get_command("github").add_command(command)
