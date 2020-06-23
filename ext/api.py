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
import datetime
import itertools
import os
import random
import textwrap
import time
from collections import namedtuple
from typing import List

import async_cse as cse
import discord
import humanize
import aiogoogletrans
from discord.ext import commands, flags

import utils.errors as errors
from config import conf
from utils.paginator import PagedEmbedMenu, CSMenu

GoogleResults = namedtuple('GoogleResults', ['title', 'description', 'result_url', 'image_url'])


def filter_posts(obj):
    checks = list()
    if p := obj.get('preview'):
        if p2 := p.get('reddit_video_preview'):
            checks.append(p2.get('is_gif') is False)
    checks.append(obj.get('is_video') is False)
    return all(checks)


async def do_translation(ctx, content, dest='en'):
    tr = aiogoogletrans.Translator()
    langs = aiogoogletrans.LANGUAGES
    translated = await tr.translate(content, dest=dest)
    embed = discord.Embed(color=discord.Color.main)
    embed.add_field(
        name=f'Input: {langs.get(translated.src, "Auto-Detected").title()}',
        value=content
    )
    embed.add_field(
        name=f'Output: {langs.get(translated.dest, "Unknown").title()}',
        value=translated.text,
        inline=False
    )
    await ctx.send(embed=embed)


def build_google_embeds(results: List[GoogleResults]):
    embeds = list()
    for r in results:
        embed = discord.Embed(color=discord.Color.main)
        embed.title = r.title
        embed.description = r.description
        embed.url = r.result_url
        if r.image_url:
            embed.set_image(url=r.image_url)
        embeds.append(embed)
    return embeds


class Api(commands.Cog):
    """Interact with various APIs"""

    def __init__(self, bot):
        self.bot = bot

    @commands.group(name='reddit', aliases=['r'], invoke_without_command=True)
    async def reddit_group(self, ctx):
        """Collection of commands made to interact with Reddit"""

    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.channel)
    async def pypi(self, ctx, *, package_name):
        """
        Search PyPi for the inputted python package
        """
        async with self.bot.session.get(f'https://pypi.org/pypi/{package_name}/json') as resp:
            if resp.status == 404:
                raise errors.ApiError(f"404 - '{package_name}' was not found")
            js = await resp.json()
        info = js['info']
        found = {
            'Home Page': info.get('home_page'),
            'Package URL': info.get('package_url')
        }
        if info.get('project_urls'):
            for key, value in info.get('project_urls').items():
                if 'doc' in key.lower() or 'issu' in key.lower():
                    found[key] = value
        embed = discord.Embed(color=discord.Color.main).set_thumbnail(url='https://i.imgur.com/UWgCSMs.png')
        embed.description = textwrap.fill(info.get('summary'), width=40)
        embed.title = f"{info.get('name')} {info['version']}"
        embed.add_field(
            name='Info',
            value='\n'.join([f'[{k}]({v})' for k, v in found.items() if v is not None]),
        )
        info2_dict = {
            '⚖️': info.get('license'),
            '<:python:596577462335307777>': info.get('requires_python')
        }
        info2 = str()
        for k, v in info2_dict.items():
            if v:
                info2 += f'{k} {discord.utils.escape_markdown(v)}\n'
        if info2:
            embed.add_field(name='_ _', value=info2)
        embed.set_footer(text=info.get('author'))
        await ctx.send(embed=embed)

    @commands.group(aliases=['tr'], invoke_without_command=True)
    async def translate(self, ctx, *, content):
        """
        Basic translation - tries to auto-detect and translate to English
        """
        await do_translation(ctx, content)

    @translate.command(name='to')
    async def translate_to(self, ctx, destination_language: str, *, content):
        """
        Translate from one language to another
        """
        await do_translation(ctx, content, destination_language)

    @commands.group(invoke_without_command=True, aliases=['g'])
    async def google(self, ctx, *, query: str):
        """
        Search Google for the query
        """
        embeds = list()
        async with ctx.loading(tick=False):
            keys = os.getenv('SEARCH_TOKENS').split(',')
            cli = cse.Search(list(keys))
            res = await cli.search(query)
            results = [GoogleResults(
                title=result.title,
               description=result.description,
                result_url=result.url,
                image_url=None) for result in res]
            embeds = build_google_embeds(results)
        await cli.close()
        if not embeds:
            return
        source = PagedEmbedMenu(embeds)
        menu = CSMenu(source, delete_on_button=True, clear_reactions_after=True)
        await menu.start(ctx)

    @google.command(aliases=['img'])
    async def image(self, ctx, *, query: str):
        """
        Search Google Images for the query
        """
        embeds = list()
        async with ctx.loading(tick=False):
            keys = os.getenv('IMAGE_TOKENS').split(',')
            cli = cse.Search(list(keys))
            res = await cli.search(query, image_search=True)
            results = [GoogleResults(
                title=result.title,
                description=result.description,
                result_url=result.url,
                image_url=result.image_url) for result in res]
            embeds = build_google_embeds(results)
        await cli.close()
        if not embeds:
            return
        source = PagedEmbedMenu(embeds)
        menu = CSMenu(source, delete_on_button=True, clear_reactions_after=True)
        await menu.start(ctx)

    @commands.group(aliases=['fn'], invoke_without_command=True)
    async def fortnite(self, ctx):
        """Various commands to interact with the Fortnite API"""
        pass

    @fortnite.command(aliases=['shop'])
    async def itemshop(self, ctx):
        """Lists out the items currently in the Fortnite item shop"""
        async with self.bot.session.get(
                'https://api.fortnitetracker.com/v1/store', headers={'TRN-Api-Key': os.getenv('FORTNITE_KEY')}) as resp:
            js = await resp.json()

        def _gather():
            for cat, grp in itertools.groupby([*js], lambda c: c.get('storeCategory')):
                yield f'<:vbuck:706533872460103731> **__{cat}__**', '\n'.join(
                    sorted(
                        [f"`{g.get('vBucks'):<4}` [`{g.get('name')}`]({g.get('imageUrl')})"
                         for g in [*grp]]))

        await ctx.quick_menu(
            [*_gather()],
            1,
            template=discord.Embed(color=discord.Color.main).set_author(
                name=str(datetime.date.today()), icon_url='https://i.imgur.com/XMTZAQT.jpg'), delete_message_after=True)

    @fortnite.command(name='stats')
    async def _fnstats(self, ctx, platform, *, epic_name):
        """
        Lists out some stats for the specified player.
            - Platform is a required argument, and can be any one of `pc`, `touch`, `xbl`, `psn`
        """
        async with self.bot.session.get(
                f'https://api.fortnitetracker.com/v1/profile/{platform}/{epic_name}',
                headers={'TRN-Api-Key': os.getenv('FORTNITE_KEY')}) as resp:
            js = await resp.json()
        embed = discord.Embed(color=discord.Color.main).set_author(
            name=js.get('epicUserHandle'), icon_url='https://i.imgur.com/XMTZAQT.jpg')
        stats = str()
        recents = str()
        checked_status = ['Wins', 'K/d', 'Matches Played', 'Kills', 'Top 5s', 'Win%']
        e = max(checked_status, key=lambda x: len(x))
        if lstats := js.get('lifeTimeStats'):
            for i in lstats:
                if i.get('key') in checked_status:
                    stats += f"{i.get('key').ljust(len(e))} {i.get('value')}\n"
            embed.add_field(
                name='Stats',
                value=f'```{stats}```'
            )
        checked_recents = ['matches', 'kills', 'top1', 'top5', 'playersOutlived', 'minutesPlayed']
        e2 = max(checked_recents, key=lambda x: len(x))
        if rstats := js.get('recentMatches'):
            for c in checked_recents:
                recents += f"{c.title().ljust(len(e2))} {rstats[0].get(c)}\n"
            embed.add_field(
                name='Recents',
                value=f'```{recents}```'
            )
        await ctx.send(embed=embed)

    @commands.group(name='github', aliases=['gh'], invoke_without_command=True)
    async def git_group(self, ctx):
        """Collection of commands made to interact with GitHub"""


def setup(bot):
    bot.add_cog(Api(bot))
