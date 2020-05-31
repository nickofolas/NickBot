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
from collections import namedtuple
import time
from datetime import datetime
from contextlib import suppress

import discord
from discord.ext import commands, flags
from humanize import naturaltime as nt

from utils.errors import ApiError
from utils.paginator import CSMenu, PagedEmbedMenu
from utils.config import conf
from utils.converters import RedditConverter

PollChoice = namedtuple('PollChoice', ['text', 'votes'])


class Poll:
    def __init__(self, poll_data):
        self.data = poll_data
        self.deadline = datetime.fromtimestamp(poll_data.get("voting_end_timestamp") / 1000)
        self.total_votes = poll_data.get("total_vote_count")

    def __iter__(self):
        for option in self.data['options']:
            yield PollChoice(text=option['text'], votes=option.get('vote_count', ''))


class Submission:
    __slots__ = ('data', 'title', 'nsfw', 'text', 'upvotes', 'comments',
                 'full_url', 'img_url', 'author', 'author_url', 'thumbnail', 'poll', 'created', 'creation_delta')
    """Wraps up a Submission"""

    def __init__(self, data):
        self.data = data
        self.title = textwrap.shorten(data.get('title'), width=252)
        self.nsfw = data.get('over_18')
        self.text = textwrap.shorten(data.get('selftext'), width=1500) if data.get('selftext') else ''
        self.upvotes = data.get('ups')
        self.comments = data.get('num_comments')
        self.full_url = "https://www.reddit.com" + data.get('permalink')
        self.img_url = data.get('url')
        self.thumbnail = data.get('thumbnail')
        self.author = data.get('author')
        self.author_url = f"https://www.reddit.com/user/{self.author}"
        self.created = data.get('created_utc')
        self.creation_delta = datetime.utcnow() - datetime.utcfromtimestamp(self.created)
        if p := data.get('poll_data'):
            self.poll = Poll(p)
        else:
            self.poll = None

    @property
    def is_gif(self):
        if p := self.data.get('preview'):
            if p2 := p.get('reddit_video_preview'):
                return p2.get('is_gif')
        return False


class SubListing:
    __slots__ = ('data', 'allow_nsfw')
    """Generates a listing of posts from a Subreddit"""

    def __init__(self, data, *, allow_nsfw=False):
        self.data = data
        self.allow_nsfw = allow_nsfw

    def do_predicates(self, submission):
        predicates = [submission.is_gif is False]
        if not self.allow_nsfw:
            predicates.append(submission.nsfw is False)
        return all(predicates)

    @property
    def posts(self):
        for post in self.data['data']['children']:
            submission = Submission(post['data'])
            if not self.do_predicates(submission):
                continue
            yield submission


class Subreddit:
    __slots__ = ('data', 'title', 'icon_img', 'prefixed', 'subscribers', 'pub_desc', 'full_url', 'created', 'nsfw')
    """Wraps up a Subreddit's JSON"""

    def __init__(self, data):
        self.data = data
        self.title = data.get('title')
        self.icon_img = data.get('icon_img')
        self.prefixed = data.get('display_name_prefixed')
        self.subscribers = data.get('subscribers')
        self.pub_desc = data.get('public_description')
        self.full_url = "https://reddit.com" + data.get('url')
        self.created = data.get('created_utc')
        self.nsfw = data.get('over18', False)


class Redditor:
    __slots__ = ('tdata', 'adata', 'subreddit', 'is_gold', 'icon_url', 'link_karma', 'comment_karma', 'name', 'created')
    """Wraps up a Redditor's JSON"""

    def __init__(self, *, about_data, trophy_data=None):
        about_data = about_data.get('data')
        self.tdata = trophy_data.get('data') if trophy_data else None
        self.adata = about_data
        self.subreddit = Subreddit(about_data.get('subreddit'))
        self.is_gold = about_data.get('is_gold')
        self.icon_url = about_data.get('icon_img')
        self.link_karma = about_data.get('link_karma')
        self.comment_karma = about_data.get('comment_karma')
        self.name = about_data.get('name')
        self.created = about_data.get('created_utc')

    @property
    def trophies(self):
        if not self.tdata:
            return None
        for trophy in self.tdata.get('trophies'):
            yield trophy['data'].get('name')


def gen_listing_embeds(listing):
    for post in listing.posts:
        desc = post.text
        if p := post.poll:
            pending = p.deadline > datetime.utcnow()
            desc = '\n'.join(f"➣ {opt.votes} votes: {opt.text}" for opt in p)
            if pending:
                desc = "**Poll pending**\n" + '\n'.join(f"➣ {opt.text}" for opt in p)
            desc += f'\n**{p.total_votes} total votes**'
        embed = discord.Embed(
            title=post.title,
            description=f"<:upvote:698744205710852167> {post.upvotes:,} | :speech_balloon: {post.comments:,} "
                        f"| 🕙 {nt(post.creation_delta)}\n{desc}",
            url=post.full_url,
            color=discord.Color.main
        ).set_image(url=post.img_url).set_author(name=post.author,
                                                 url=f"https://www.reddit.com/user/{post.author}")
        yield embed


# noinspection PyMethodParameters,PyUnresolvedReferences
class Reddit(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @flags.add_flag('sub', nargs='?')
    @flags.add_flag('-s', '--sort', choices=['top', 'new', 'rising', 'hot', 'controversial', 'best'], default='hot')
    @flags.add_flag('-a', '--amount', type=int, default=5)
    @flags.add_flag('-t', '--time', choices=['hour', 'day', 'week', 'month', 'year', 'all'], default='all')
    @flags.command(name='redditposts', aliases=['posts'])
    async def reddit_posts(ctx, **flags):
        """Get posts from a subreddit"""
        sub = await RedditConverter().convert(ctx, flags['sub'])
        async with ctx.loading(tick=False, exc_ignore=KeyError), ctx.bot.session.get(
                f'https://www.reddit.com/r/{sub}/{flags["sort"]}.json',
                params={'limit': '100', 't': flags['time']}) as resp:
            data = await resp.json()
        if resp.status != 200:
            raise ApiError(f'Recieved {resp.status}')
        embeds = [*gen_listing_embeds(SubListing(data, allow_nsfw=ctx.channel.is_nsfw()))]
        if not embeds:
            raise ApiError("Couldn't find any posts that matched the contextual criteria")
        source = PagedEmbedMenu(embeds[:flags['amount']])
        menu = CSMenu(source, delete_message_after=True)
        await menu.start(ctx)

    @commands.command(name='user')
    async def reddit_user(ctx, *, user: RedditConverter):
        """Get user info on a redditor"""
        async with ctx.loading(tick=False), \
                ctx.bot.session.get(f"https://reddit.com/user/{user}/about.json") as r1, \
                ctx.bot.session.get(f"https://reddit.com/user/{user}/trophies.json") as r2:
            about, trophies = (await r1.json(), await r2.json())
        if r1.status != 200 or r2.status != 200:
            raise ApiError(f"Recieved {r1.status}, {r2.status}")
        user = Redditor(about_data=about, trophy_data=trophies)
        tstring = textwrap.fill(' '.join([conf['trophy_emojis'].get(t, '') for t in set(user.trophies)]), 225)
        embed = discord.Embed(
            title=user.subreddit.title if user.subreddit.title != user.name else '',
            description=tstring,
            color=discord.Color.main).set_author(name=user.subreddit.prefixed, url=user.subreddit.full_url)
        embed.set_thumbnail(url=user.icon_url.split('?', 1)[0])
        embed.add_field(
            name='<:karma:701164781238878270> Karma',
            value=textwrap.dedent(f"""
                **{user.link_karma + user.comment_karma:,}** combined
                **{user.comment_karma:,}** comment
                **{user.link_karma:,}** post
                """))
        embed.set_footer(text=f"Created {nt(time.time() - user.created)}")
        await ctx.send(embed=embed)

    @commands.command(name='subreddit', aliases=['sub'])
    async def reddit_subreddit(ctx, *, subreddit: RedditConverter):
        """Returns brief information on a subreddit"""
        async with ctx.loading(exc_ignore=KeyError, tick=False), ctx.bot.session.get(f"https://reddit.com/r/{subreddit}/about.json") as resp:
            data = (await resp.json())['data']
        if resp.status != 200:
            raise ApiError(f'Recieved {resp.status}')
        sub = Subreddit(data)
        embed = discord.Embed(title=sub.prefixed, url=sub.full_url, color=discord.Color.main)
        embed.set_thumbnail(url='https://i.imgur.com/gKzmGxt.png' if sub.nsfw and not ctx.channel.is_nsfw() else sub.icon_img)
        embed.description = f"**Title** {sub.title}"
        embed.description += f"\n**Subs** {sub.subscribers:,}"
        embed.description += f"\n**Created** {nt(time.time() - sub.created)}"
        await ctx.send(embed=embed)


def setup(bot):
    for command in Reddit(bot).get_commands():
        bot.get_command('reddit').remove_command(command.name)
        bot.get_command('reddit').add_command(command)
