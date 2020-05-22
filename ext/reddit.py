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
from discord.ext import commands, flags

from utils.errors import ApiError
from utils.paginator import CSMenu, PagedEmbedMenu


class Submission:
    def __init__(self, data):
        self.data = data
        self.title = textwrap.shorten(data.get('title'), width=252)
        self.nsfw = data.get('over_18')
        self.text = textwrap.shorten(data.get('selftext'), width=1500) if data.get('selftext') else ''
        self.upvotes = data.get('ups')
        self.comments = data.get('num_comments')
        self.full_url = "https://www.reddit.com" + data.get('permalink')
        self.img_url = data.get('url')
        self.author = data.get('author')
        self.author_url = f"https://www.reddit.com/user/{self.author}"

    @property
    def is_gif(self):
        if p := self.data.get('preview'):
            if p2 := p.get('reddit_video_preview'):
                return p2.get('is_gif')
        return False


class SubListing:
    def __init__(self, data, *, allow_nsfw=False):
        self.data = data
        self.allow_nsfw = allow_nsfw

    def do_predicates(self, submission):
        predicates = [submission.is_gif is False]
        if self.allow_nsfw:
            predicates.append(submission.nsfw is False)
        return all(predicates)

    @property
    def posts(self):
        for post in self.data['data']['children']:
            submission = Submission(post['data'])
            if not self.do_predicates(submission):
                continue
            yield submission


def gen_listing_embeds(listing):
    for post in listing.posts:
        embed = discord.Embed(
            title=post.title,
            description=f"<:upvote:698744205710852167> {post.upvotes} :speech_balloon: {post.comments}\n{post.text}",
            url=post.full_url,
            color=discord.Color.main
        ).set_image(url=post.img_url).set_author(name=post['author'],
                                                 url=f"https://www.reddit.com/user/{post['author']}")
        yield embed


# noinspection PyMethodParameters,PyUnresolvedReferences
class Reddit(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @flags.add_flag('sub', nargs='?')
    @flags.add_flag('-s', '--sort', choices=['top', 'new', 'rising', 'hot', 'controversial', 'best'], default='hot')
    @flags.add_flag('-a', '--amount', type=int, default=5)
    @flags.command(name='redditposts', aliases=['posts'])
    async def reddit_posts(ctx, **flags):
        async with ctx.loading(tick=False), ctx.bot.session.get(
                f'https://www.reddit.com/r/{flags["sub"].replace("r/", "")}/{flags["sort"]}.json') as resp:
            if resp.status != 200:
                raise ApiError(f'Recieved {resp.status}')
            data = await resp.json()
        embeds = [*gen_listing_embeds(SubListing(data, allow_nsfw=ctx.channel.is_nsfw()))]
        source = PagedEmbedMenu(embeds)
        menu = CSMenu(source, delete_message_after=True)
        await menu.start(ctx)


def setup(bot):
    for command in Reddit(bot).get_commands():
        bot.get_command('reddit').remove_command(command.name)
        bot.get_command('reddit').add_command(command)
