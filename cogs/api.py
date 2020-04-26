import random
import os
import time

import discord
from discord.ext import commands
import humanize
import aiohttp
from aiogoogletrans import LANGUAGES as langs
from aiogoogletrans import Translator
import async_cse as cse
import aiosqlite as asq

import utils.errors as errors
from utils.paginator import GoogleMenu, CSMenu
from utils.config import conf
from utils.checks import exclude_channels


async def do_translation(self, ctx, input, dest='en'):
    tr = Translator()
    translated = await tr.translate(input, dest=dest)
    embed = discord.Embed(color=discord.Color.main)
    embed.add_field(
        name=f'Input: {langs.get(translated.src, "Auto-Detected").title()}',
        value=input
    )
    embed.add_field(
        name=f'Output: {langs.get(translated.dest, "Unknown").title()}',
        value=translated.text,
        inline=False
    )
    await ctx.send(embed=embed)


async def get_sub(self, ctx, sort, subreddit, safe=True):
    parameters = {
        'limit': '100'
    }
    if sort not in ['top', 'new', 'rising', 'hot', 'controversial', 'best']:
        raise errors.SortError(f"'{sort}' is not a valid sort option")
    if sort == 'top':
        parameters['t'] = 'all'
    async with ctx.typing(), self.bot.session.get(
            f'https://www.reddit.com/r/{subreddit}/{sort}.json',
            params=parameters) as r:
        if r.status == 404:
            raise errors.SubredditNotFound(f"'{subreddit}' was not found")
        if r.status == 403:
            raise errors.ApiError(f"Received 403 Forbidden - 'r/{subreddit}' is likely set to private")
        res = await r.json()  # returns dict
        no_videos = list()
        for p in res['data']['children']:
            try:
                if p['data'].get('preview').get('reddit_video_preview').get('is_gif') is True:
                    continue
            except AttributeError:
                pass
            if p['data'].get('is_video') is True:
                continue
            no_videos.append(p)
        if safe is True:
            no_videos = [
                p for p in no_videos
                if p['data']['over_18'] is False
            ]
        try:
            post = random.choice(no_videos)
        except IndexError:
            raise commands.CommandError('No SFW posts found')
        if post['data']['selftext']:
            text = (post['data']['selftext'][:1500] + '...') if len(post['data']['selftext']) > 1500 else post['data']['selftext']
        else:
            text = ''
        post_delta = time.time()-post['data']['created_utc']
        embed = discord.Embed(
            title=(post['data']['title'][:252] + '...') if len(post['data']['title']) > 252 else post['data']['title'],
            description=
            (f"**<:upvote:698744205710852167> {post['data']['ups']} | {post['data']['num_comments']} :speech_balloon:**\n {text}"),
            url="https://www.reddit.com" + post['data']['permalink'],
            color=discord.Color.main)
        embed.set_image(
            url=post['data']['url'])
        embed.set_footer(text=f'r/{post["data"]["subreddit"]} | Submitted {humanize.naturaltime(post_delta)}')
        embed.set_author(
            name=post['data']['author'],
            url=f"https://www.reddit.com/user/{post['data']['author']}"
            )
    return post, embed


async def q(self, subreddit, p):
    async with self.bot.session.get(f'https://www.reddit.com/r/{subreddit}/about/modqueue/.json', params=p) as r:
        retrieved = await r.json()  # returns dict
    return retrieved


class Api(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.group(invoke_without_command=True)
    async def rand(self, ctx, sort, subreddit):
        """Asynchronously get a random post from a sort on a subreddit"""
        post, embed = await get_sub(self, ctx, sort, subreddit)
        await ctx.send(embed=embed)

    @rand.command(hidden=True)
    @commands.is_owner()
    async def bypass(self, ctx, sort, subreddit):
        post, embed = await get_sub(self, ctx, sort, subreddit, safe=False)
        await ctx.send(embed=embed)

    @commands.command(aliases=['modqueue', 'modq'])
    async def queue(self, ctx, subreddit='mod'):
        """Get the modqueue of a sub, defaults to combined queue"""
        p2 = {
            'feed': os.getenv("FEED"),
            'user': 'nickofolas',
            'limit': '100',
            'only': 'comments'
            }
        p = {
            'feed': os.getenv("FEED"),
            'user': 'nickofolas',
            'limit': '100',
            'only': 'links'
            }
        start = time.perf_counter()
        async with ctx.typing():
            ret2 = await q(self, subreddit, p2)
            ret = await q(self, subreddit, p)
            posts = []
            comments = []
            aft = ret['data']['after']
            aft2 = ret2['data']['after']
            while True:
                p = {
                    'feed': os.getenv("FEED"),
                    'user': 'nickofolas',
                    'limit': '100', 'only': 'links',
                    'after': aft
                    }
                try:
                    r = await q(self, subreddit, p)
                    posts.append(len(r['data']['children']))
                    aft = r['data']['after']
                except Exception:
                    break
            while True:
                p2 = {
                    'feed': os.getenv("FEED"),
                    'user': 'nickofolas',
                    'limit': '100', 'only':
                    'comments',
                    'after': aft2
                    }
                try:
                    r2 = await q(self, subreddit, p2)
                    comments.append(len(r2['data']['children']))
                    aft2 = r2['data']['after']
                except Exception:
                    break
            end = time.perf_counter()
            embed = discord.Embed(
                title=f'Modqueue for r/{subreddit}',
                description=
                f"Posts in queue: {len(ret['data']['children']) + sum(posts)}\nComments in queue: {len(ret2['data']['children']) + sum(comments)}",
                url=f'https://www.reddit.com/r/{subreddit}/about/modqueue',
                color=discord.Color.main)
            embed.set_footer(text=f'Fetched in {(end - start):.3f}s')
            await ctx.send(embed=embed)

    @commands.group(invoke_without_command=True, aliases=['sub'])
    async def subreddit(self, ctx, *, subreddit):
        async with self.bot.session.get(f'https://reddit.com/r/{subreddit}/about/.json') as resp:
            if resp.status == 404:
                raise errors.SubredditNotFound(f"'{subreddit}' was not found")
            js = (await resp.json())['data']
        embed = discord.Embed(
            title=js['display_name_prefixed'],
            url=f"https://reddit.com{js['url']}",
            color=discord.Color.main).set_thumbnail(
                url=js['icon_img'])
        embed.description = f"""
**Title** {js['title']}
**Created** {humanize.naturaltime(time.time() - js['created_utc'])}
**Subscribers** {js['subscribers']:,}
"""
        if js['over18'] is True:
            embed.description += '**Content Warning** NSFW'
            embed.set_thumbnail(url='')
        await ctx.send(embed=embed)

    @commands.group(invoke_without_command=True, aliases=['r'])
    async def redditor(self, ctx, *, user=None):
        """Overview of a reddit user"""
        if user is None:
            async with asq.connect('./database.db') as db:
                usr_get = await db.execute("SELECT default_reddit FROM user_data WHERE user_id=$1", (ctx.author.id,))
                user = (await usr_get.fetchone())[0]
                if user is None:
                    raise commands.CommandError(
                        'You have no default user set. Please see '
                        f'the `{ctx.prefix}redditor default` command to set one.')
        else:
            user = user.replace('u/', '')
        async with self.bot.session.get(f'https://www.reddit.com/user/{user}/about/.json') as resp:
            if resp.status == 404:
                raise errors.ApiError(f'u/{user} was not found')
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
            description=''.join(set(trophy_list)) + ctx.tab(),
            color=discord.Color.main).set_author(
                name=usr['subreddit']['display_name_prefixed'],
                url=f'https://www.reddit.com/user/{user}',
                icon_url='https://i.imgur.com/mlZRTzi.png' if usr['is_gold'] is True else ''
            ).set_thumbnail(url=usr['icon_img'].split('?', 1)[0])
        embed.add_field(
            name='<:karma:701164781238878270> Karma',
            value=f"""
**{usr['link_karma'] + usr['comment_karma']:,}** combined
**{usr['comment_karma']:,}** comment
**{usr['link_karma']:,}** post
            """)
        embed.set_footer(
            text=f'Account created {humanize.naturaltime(time.time() - usr["created_utc"])}'
        )
        await ctx.send(embed=embed)

    @redditor.command(aliases=['mod'])
    async def modstats(self, ctx, user=None):
        """View moderator stats for a redditor"""
        if user is None:
            async with asq.connect('./database.db') as db:
                usr_get = await db.execute("SELECT default_reddit FROM user_data WHERE user_id=$1", (ctx.author.id,))
                user = (await usr_get.fetchone())[0]
                if user is None:
                    raise commands.CommandError('You have no default user set')
        async with self.bot.session.get(f'https://www.reddit.com/user/{user}/moderated_subreddits/.json') as r:
            js = await r.json()
        async with self.bot.session.get(f'https://www.reddit.com/user/{user}/about.json?raw_json=1') as r:
            profile_js = await r.json()
        total_modded = '{:,}'.format(sum(sub['subscribers'] for sub in js['data']))
        top_20 = []
        for sub in js['data']:
            if len(top_20) == 15:
                break
            top_20.append(f'[{sub["sr_display_name_prefixed"]}](https://www.reddit.com{sub["url"]})')
        embed = discord.Embed(
            title='',
            description=f'**Mod Stats for [u/{user}](https://www.reddit.com/user/{user})**',
            color=discord.Color.main)
        embed.set_thumbnail(url=profile_js['data']['icon_img'])
        embed.add_field(name='Total Subscribers', value=total_modded)
        embed.add_field(name='No. Subs Modded', value=len(js['data']))
        embed.add_field(name=f'Top {len(top_20)} Subreddits', value='\n'.join(top_20), inline=False)
        await ctx.send(embed=embed)

    @redditor.command(aliases=['def'])
    async def default(self, ctx, *, reddit_user):
        """Set a shortcut to your reddit user for reddit commands
        This will allow you to access your reddit acc info without passing an argument """
        async with asq.connect('./database.db') as db:
            await db.execute("UPDATE user_data SET default_reddit=$1 WHERE user_id=$2", (reddit_user, ctx.author.id))
            await db.commit()
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
            value=f"""
**Total Cases: **{js['cases']:,}
**Total deaths: **{js['deaths']:,}
**Recovered Cases: **{js['recovered']:,}
                """
                )
        if country != 'global':
            embed.add_field(
                name='More Stats',
                value=f"""
**Critical Cases: **{js['critical']:,}
**Total Tests: **{js['totalTests']:,}
**Tests/mil: **{js['testsPerOneMillion']:,}
**Cases/mil: **{js['casesPerOneMillion']:,}
**Deaths/mil: **{js['deathsPerOneMillion']:,}
                """
            )
        await ctx.send(embed=embed)

    @commands.command()
    async def pypi(self, ctx, *, package_name):
        """
        Search PyPi for the inputted python package
        """
        async with self.bot.session.get(f'https://pypi.org/pypi/{package_name}/json') as resp:
            if resp.status == 404:
                raise errors.ApiError(f"404 - '{package_name}' was not found")
            js = await resp.json()
        home_link = js['info'].get('home_page', 'No home page url found')
        docs_link = js['info']['project_urls'].get('Documentation', 'No documentation link found')
        pkg_url = js['info'].get('package_url', 'No package url found')
        embed = discord.Embed(color=discord.Color.main)
        embed.description = js['info']['summary']
        embed.title = js['info']['name']
        embed.set_author(name=js['info']['author'])
        embed.add_field(
            name='Links',
            value=f"""
Home Page: {home_link}
Documentation: {docs_link}
Package URL: {pkg_url}
            """,
            )
        embed.set_footer(text=f"Version: {js['info']['version']}")
        await ctx.send(embed=embed)

    @commands.group(aliases=['trans'], invoke_without_command=True)
    async def translate(self, ctx, *, input):
        """
        Basic translation - tries to auto-detect and translate to English
        """
        await do_translation(self, ctx, input)

    @translate.command(name='to')
    async def translate_to(self, ctx, destination_language: str, *, input):
        """
        Translate from one language to another
        """
        await do_translation(self, ctx, input, destination_language)

    @commands.group(invoke_without_command=True, aliases=['g'])
    async def google(self, ctx, *, query: str):
        """
        Search Google for the query
        """
        keys = os.getenv('SEARCH_TOKENS').split(',')
        cli = cse.Search(list(keys))
        page_entries = []
        res = await cli.search(query)
        await cli.close()
        for result in res:
            res_tup = (result.title, result.description, result.url, result.image_url)
            page_entries.append(res_tup)
        source = GoogleMenu(page_entries, per_page=1)
        menu = CSMenu(source, delete_message_after=True)
        await menu.start(ctx)

    @google.command(aliases=['img'])
    async def image(self, ctx, *, query: str):
        """
        Search Google Images for the query
        """
        keys = os.getenv('IMAGE_TOKENS').split(',')
        cli = cse.Search(list(keys))
        page_entries = []
        res = await cli.search(query, image_search=True)
        await cli.close()
        for result in res:
            res_tup = (result.title, result.description, result.url, result.image_url)
            page_entries.append(res_tup)
        source = GoogleMenu(page_entries, per_page=1, image=True)
        menu = CSMenu(source, delete_message_after=True)
        await menu.start(ctx)

    @commands.command(name="cleverbot", aliases=["cb", "ask"])
    @commands.cooldown(1, 5, commands.BucketType.user)
    @exclude_channels(665249180150792216)
    async def cleverbot_(self, ctx, *, query: str):
        """Ask Cleverbot a question!"""
        async with ctx.ExHandler(propagate=(self.bot, ctx)), ctx.typing():
            r = await self.bot.cleverbot.ask(query, ctx.author.id)
            await ctx.send("{}, {}".format(ctx.author.mention, r.text))

    def cog_unload(self):
        self.bot.loop.create_task(self.bot.cleverbot.close())


def setup(bot):
    bot.add_cog(Api(bot))
