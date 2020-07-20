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

import async_cse as cse
import discord
import humanize
import aiogoogletrans
from discord.ext import commands, flags

import neo
import neo.utils.errors as errors
from neo.utils.paginator import PagedEmbedMenu, CSMenu


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
    embed = neo.Embed()
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


def build_google_embeds(results, show_images=True):
    embeds = list()
    for r in results:
        embed = neo.Embed()
        embed.title = r.title
        embed.description = r.description
        embed.url = r.url
        if show_images and r.image_url:
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
        Search PyPI for the inputted python package
        """
        async with self.bot.session.get(f'https://pypi.org/pypi/{package_name}/json') as resp:
            if resp.status == 404:
                raise errors.ApiError(f"404 - '{package_name}' was not found")
            js = await resp.json()
        info = js['info']
        found = {'PyPI Page': info.get('package_url'), 'Home Page': info.get('home_page'),
                 'Release History': f"https://pypi.org/project/{package_name}/#history"}
        if (p_urls := info.get('project_urls')):
            for key, value in p_urls.items():
                if key.lower().startswith(('doc', 'issu')):
                    found[key] = value
        deps = len(info.get('requires_dist') or [])
        embed = neo.Embed().set_thumbnail(url='https://i.imgur.com/UWgCSMs.png')
        embed.description = textwrap.fill(info.get('summary', ''), width=40)
        embed.title = f"{info.get('name')} {info['version']}"
        embed.add_field(name='Info', value='\n'.join([f'[{k}]({v})' for k, v in found.items() if v is not None]))
        embed.add_field(
            name='_ _', 
            value=f"⚖️  {info.get('license') or 'No license'}\n"
                  f"<:python:596577462335307777> {info.get('requires_python') or 'Not specified'}\n"
                  f"<:pypideps:729920158193287208> {deps} dependenc{'y' if deps == 1 else 'ies'}")
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
            keys = neo.secrets.gsearch_keys
            cli = cse.Search(keys, session=self.bot.session)
            res = await cli.search(query)
            embeds = build_google_embeds(res, show_images=False)
        if not embeds:
            return
        source = PagedEmbedMenu(embeds)
        menu = CSMenu(source, delete_on_button=True, clear_reactions_after=True)
        await menu.start(ctx)

    @google.command(aliases=['img', 'i'])
    @commands.is_nsfw()
    async def image(self, ctx, *, query: str):
        """
        Search Google Images for the query
        """
        embeds = list()
        async with ctx.loading(tick=False):
            keys = neo.secrets.gimage_keys
            cli = cse.Search(keys, session=self.bot.session)
            res = await cli.search(query, image_search=True)
            embeds = build_google_embeds(res)
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
                'https://api.fortnitetracker.com/v1/store', headers={'TRN-Api-Key': neo.secrets.fortnite_key}) as resp:
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
            template=neo.Embed().set_author(
                name=str(datetime.date.today()), icon_url='https://i.imgur.com/XMTZAQT.jpg'), delete_message_after=True)

    @fortnite.command(name='stats')
    async def _fnstats(self, ctx, platform, *, epic_name):
        """
        Lists out some stats for the specified player.
            - Platform is a required argument, and can be any one of `pc`, `touch`, `xbl`, `psn`
        """
        async with self.bot.session.get(
                f'https://api.fortnitetracker.com/v1/profile/{platform}/{epic_name}',
                headers={'TRN-Api-Key': neo.secrets.fortnite_key}) as resp:
            js = await resp.json()
        embed = neo.Embed().set_author(
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
