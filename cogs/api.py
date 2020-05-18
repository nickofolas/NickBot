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

import aiohttp
import async_cse as cse
import discord
import humanize
import aiogoogletrans
from discord.ext import commands, flags

import utils.errors as errors
from utils.config import conf
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


async def get_sub(self, ctx, *, sort, subreddit, safe, amount=5):
    parameters = {'limit': '100'}
    if sort == 'top':
        parameters['t'] = 'all'
    async with ctx.typing(), self.bot.session.get(
            f'https://www.reddit.com/r/{subreddit.replace("r/", "")}/{sort}.json',
            params=parameters) as r:
        if r.status == 404:
            raise errors.SubredditNotFound(f"'{subreddit}' was not found")
        if r.status == 403:
            raise errors.ApiError(f"Received 403 Forbidden - 'r/{subreddit}' is likely set to private")
        res = await r.json()
        listing = [p['data'] for p in res['data']['children']]
        if safe is True:
            listing = list(filter(lambda p: p.get('over_18') is False, listing))
        try:
            posts = random.sample(list(filter(filter_posts, listing)), k=amount)
        except ValueError:
            raise commands.CommandError('No SFW posts found')
        embeds = list()
        for post in posts:
            text = textwrap.shorten(post['selftext'], width=1500) if post['selftext'] else ''
            embed = discord.Embed(
                title=textwrap.shorten(post['title'], width=252),
                description=f"**<:upvote:698744205710852167> {post['ups']} | {post['num_comments']} "
                            f":speech_balloon:**\n {text}",
                url="https://www.reddit.com" + post['permalink'],
                color=discord.Color.main)
            embed.set_image(url=post['url'])
            embed.set_author(name=post['author'], url=f"https://www.reddit.com/user/{post['author']}")
            embeds.append(embed)
    return embeds


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

    @flags.add_flag('sub', nargs='?')
    @flags.add_flag('-s', '--sort', choices=['top', 'new', 'rising', 'hot', 'controversial', 'best'], default='hot')
    @flags.add_flag('-a', '--amount', type=int, default=5)
    @flags.command(name='redditposts', aliases=['rposts'])
    async def _flags_reddit(self, ctx, **flags):
        """Get posts from a subreddit"""
        embeds = await get_sub(self, ctx, sort=flags['sort'], subreddit=flags['sub'], amount=flags['amount'], safe=not ctx.channel.nsfw)
        source = PagedEmbedMenu(embeds)
        menu = CSMenu(source, delete_message_after=True)
        await menu.start(ctx)

    @commands.command(aliases=['subinfo'])
    async def subredditinfo(self, ctx, *, subreddit):
        """Get some quick info on the named subreddit"""
        async with self.bot.session.get(f'https://reddit.com/r/{subreddit}/about/.json') as resp:
            if resp.status == 404:
                raise errors.SubredditNotFound(f"'{subreddit}' was not found")
            js = (await resp.json())['data']
        embed = discord.Embed(
            title=js['display_name_prefixed'],
            url=f"https://reddit.com{js['url']}",
            color=discord.Color.main).set_thumbnail(
            url=js['icon_img'])
        embed.description = textwrap.dedent(f"""
        **Title** {js['title']}
        **Created** {humanize.naturaltime(time.time() - js['created_utc'])}
        **Subscribers** {js['subscribers']:,}
        """)
        if js['over18'] is True:
            embed.description += '**Content Warning** NSFW'
            embed.set_thumbnail(url='')
        await ctx.send(embed=embed)

    @commands.group(invoke_without_command=True, aliases=['r'])
    async def redditor(self, ctx, *, user=None):
        """Overview of a reddit user"""
        if user is None:
            try:
                user = \
                    (await self.bot.conn.fetch('SELECT default_reddit FROM user_data WHERE user_id=$1', ctx.author.id))[
                        0][
                        'default_reddit']
                if user is None:
                    raise IndexError
            except IndexError:
                raise commands.CommandError("You do not appear to have set a default reddit account yet, please do so "
                                            "before calling this command with no arguments")
        else:
            user = user.replace('u/', '')
        async with self.bot.session.get(f'https://www.reddit.com/user/{user}/about/.json') as resp:
            if resp.status == 404:
                raise errors.ApiError(f'User was not found')
            usr = (await resp.json())['data']
        async with self.bot.session.get(f'https://www.reddit.com/user/{user}/trophies/.json') as resp:
            trophies = await resp.json()
        trophy_list = []
        for t in trophies['data']['trophies']:
            trophy_list.append(conf['trophy_emojis'].get(t['data']['name'], ''))
        alt_name = usr['subreddit'].get('title')
        alt_disp_name = alt_name if alt_name != usr['name'] else ''
        embed = discord.Embed(
            title=alt_disp_name,
            description=textwrap.fill(' '.join(set(trophy_list)), 225),
            color=discord.Color.main).set_author(
            name=usr['subreddit']['display_name_prefixed'],
            url=f'https://www.reddit.com/user/{user}',
            icon_url='https://i.imgur.com/mlZRTzi.png' if usr['is_gold'] is True else ''
        ).set_thumbnail(url=usr['icon_img'].split('?', 1)[0])
        embed.add_field(
            name='<:karma:701164781238878270> Karma',
            value=textwrap.dedent(f"""
            **{usr['link_karma'] + usr['comment_karma']:,}** combined
            **{usr['comment_karma']:,}** comment
            **{usr['link_karma']:,}** post
            """))
        embed.set_footer(
            text=f'Account created {humanize.naturaltime(time.time() - usr["created_utc"])}'
        )
        await ctx.send(embed=embed)

    @redditor.command(aliases=['mod'])
    async def modstats(self, ctx, user=None):
        """View moderator stats for a redditor"""
        if user is None:
            try:
                user = (await self.bot.conn.fetch('SELECT default_reddit FROM user_data WHERE user_id=$1',
                                                  ctx.author.id))[0]['default_reddit']
                if user is None:
                    raise IndexError
            except IndexError:
                raise commands.CommandError("You do not appear to have set a default reddit account yet, please do so "
                                            "before calling this command with no arguments")
        else:
            user = user.replace('u/', '')
        async with self.bot.session.get(f'https://www.reddit.com/user/{user}/moderated_subreddits/.json') as r:
            js = await r.json()
        async with self.bot.session.get(f'https://www.reddit.com/user/{user}/about.json?raw_json=1') as r:
            profile_js = await r.json()
        total_modded = '{:,}'.format(sum(sub['subscribers'] for sub in js.get('data', [])))
        top_20 = []
        for sub in js.get('data', []):
            if len(top_20) == 15:
                break
            top_20.append(f'[{sub["sr_display_name_prefixed"]}](https://www.reddit.com{sub["url"]})')
        embed = discord.Embed(
            title='',
            description=f'**Mod Stats for [{profile_js["data"]["subreddit"]["display_name_prefixed"]}](https://www'
                        f'.reddit.com/user/{user})**',
            color=discord.Color.main)
        embed.set_thumbnail(url=profile_js['data']['icon_img'])
        if data := js.get('data'):
            embed.add_field(name='Total Subscribers', value=total_modded)
            embed.add_field(name='No. Subs Modded', value=str(len(data)))
            embed.add_field(name=f'Top {len(top_20)} Subreddits', value='\n'.join(top_20), inline=False)
        else:
            embed.add_field(name='_ _', value='This user does not mod any subs')
        await ctx.send(embed=embed)

    @redditor.command(aliases=['def'])
    async def default(self, ctx, *, reddit_user):
        """Set a shortcut to your reddit user for reddit commands
        This will allow you to access your reddit acc info without passing an argument"""
        await self.bot.conn.execute("UPDATE user_data SET default_reddit=$1 WHERE user_id=$2",
                                    reddit_user, ctx.author.id)
        await ctx.message.add_reaction(ctx.tick(True))

    @commands.command()
    async def covid(self, ctx, *, country='global'):
        """
        Get the latest stats on COVID-19 for a country or the world
        """
        url = 'https://coronavirus-19-api.herokuapp.com/'
        if country == 'global':
            url += 'all'
        else:
            url += f'countries/{country}'
        async with self.bot.session.get(url) as resp:
            try:
                js = await resp.json()
            except aiohttp.ContentTypeError:
                raise errors.CountryNotFound(f"Country '{country}' not found.")
        embed = discord.Embed(color=discord.Color.main).set_author(name=f'{country.title()} COVID-19')
        embed.add_field(
            name='Cases',
            value=textwrap.dedent(f"""
            **Total Cases: **{js['cases']:,}
            **Total deaths: **{js['deaths']:,}
            **Recovered Cases: **{js['recovered']:,}
            """)
        )
        if country != 'global':
            embed.add_field(
                name='More Stats',
                value=textwrap.dedent(f"""
                **Critical Cases: **{js['critical']:,}
                **Total Tests: **{js['totalTests']:,}
                **Tests/mil: **{js['testsPerOneMillion']:,}
                **Cases/mil: **{js['casesPerOneMillion']:,}
                **Deaths/mil: **{js['deathsPerOneMillion']:,}
                """)
            )
        await ctx.send(embed=embed)

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
                info2 += f'{k} {v}\n'
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
        keys = os.getenv('SEARCH_TOKENS').split(',')
        cli = cse.Search(list(keys))
        res = await cli.search(query)
        await cli.close()
        results = [GoogleResults(
            title=result.title,
            description=result.description,
            result_url=result.url,
            image_url=result.image_url) for result in res]
        embeds = build_google_embeds(results)
        source = PagedEmbedMenu(embeds)
        menu = CSMenu(source, delete_message_after=True)
        await menu.start(ctx)

    @google.command(aliases=['img'])
    async def image(self, ctx, *, query: str):
        """
        Search Google Images for the query
        """
        keys = os.getenv('IMAGE_TOKENS').split(',')
        cli = cse.Search(list(keys))
        res = await cli.search(query, image_search=True)
        await cli.close()
        results = [GoogleResults(
            title=result.title,
            description=result.description,
            result_url=result.url,
            image_url=result.image_url) for result in res]
        embeds = build_google_embeds(results)
        source = PagedEmbedMenu(embeds)
        menu = CSMenu(source, delete_message_after=True)
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


def setup(bot):
    bot.add_cog(Api(bot))
