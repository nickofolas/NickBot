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
import time
from collections import namedtuple
from contextlib import suppress
from datetime import datetime

import aiohttp
import discord
import neo
from discord.ext import commands, flags
from humanize import naturaltime as nt
from neo.models import Redditor, SubListing, Submission, Subreddit
from neo.utils.converters import ArbitraryRedditConverter, RedditConverter
from neo.utils.errors import ApiError
from neo.utils.formatters import group
from neo.utils.paginator import CSMenu, PagedEmbedMenu

reddit_emojis = neo.conf["emojis"]["reddit"]


def submission_to_embed(submission):
    desc = submission.text
    if p := submission.poll:
        pending = p.deadline > datetime.utcnow()
        desc = "\n".join(f"➣ {opt.votes} votes: {opt.text}" for opt in p)
        if pending:
            desc = "**Poll pending**\n" + "\n".join(f"➣ {opt.text}" for opt in p)
        desc += f"\n**{p.total_votes} total votes**"
    embed = (
        neo.Embed(
            title=submission.title,
            description=f"{reddit_emojis['upvote']} {submission.upvotes:,} | :speech_balloon: {submission.comments:,} "
            f"| 🕙 {nt(submission.creation_delta)}\n{desc}",
            url=submission.full_url,
        )
        .set_image(url=submission.img_url)
        .set_author(
            name=submission.author,
            url=f"https://www.reddit.com/user/{submission.author}",
        )
    )
    return embed


def allow_nsfw_in_channel(channel):
    if isinstance(channel, discord.DMChannel):
        return True
    elif channel.is_nsfw():
        return True


async def post_callback(ctx, post):
    embeds = [submission_to_embed(post)]
    for item in group(post.original_json[1]["data"]["children"], 5):
        embed = neo.Embed(title="Browsing top-level comments")
        for comment in item:
            embed.add_field(
                name=f"{reddit_emojis['upvote']} {comment['data'].get('ups')} | "
                f"u/{comment['data'].get('author')}",
                value=f"[🔗](https://reddit.com{comment['data'].get('permalink')})"
                f"{textwrap.shorten(comment['data'].get('body', ''), width=125)}",
                inline=False,
            )
        embeds.append(embed)
    source = PagedEmbedMenu(embeds)
    menu = CSMenu(source, delete_message_after=True)
    await menu.start(ctx)


async def user_callback(ctx, user):
    tstring = textwrap.fill(
        " ".join(
            sorted(
                reddit_emojis["trophies"].get(t, "")
                for t in {
                    *user.trophies,
                }
            )
        ),
        225,
    )
    embed = neo.Embed(title=user.display_name, description=tstring)
    embed.set_author(
        name=user.subreddit.prefixed,
        url=user.subreddit.full_url,
        icon_url="https://i.imgur.com/6OedixC.png" if user.is_cakeday() else "",
    )
    embed.set_thumbnail(url=user.icon_url.split("?", 1)[0])
    embed.add_field(
        name=f'{reddit_emojis["karma"]} Karma',
        value=textwrap.dedent(
            f"""
            **{user.link_karma + user.comment_karma:,}** combined
            **{user.comment_karma:,}** comment
            **{user.link_karma:,}** post
            """
        ),
    )
    embed.set_footer(text=f"Created {nt(time.time() - user.created)}")
    await ctx.send(embed=embed)


async def subreddit_callback(ctx, sub):
    embed = neo.Embed(title=sub.prefixed, url=sub.full_url)
    embed.set_thumbnail(
        url="https://i.imgur.com/gKzmGxt.png"
        if sub.nsfw and not allow_nsfw_in_channel(ctx.channel)
        else sub.icon_img or ""
    )
    embed.description = f"**Title** {sub.title}"
    embed.description += f"\n**Subs** {sub.subscribers:,}"
    embed.description += f"\n**Created** {nt(time.time() - sub.created)}"
    await ctx.send(embed=embed)


callback_mapping = {
    Submission: post_callback,
    Redditor: user_callback,
    Subreddit: subreddit_callback,
}


async def delegate_callbacks(ctx, entity):
    await callback_mapping[type(entity)](ctx, entity)


class Reddit(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="get")
    async def reddit_arbitrary(ctx, *, entity: ArbitraryRedditConverter):
        """
        Fetch information on an arbitrary Reddit entity type.
        There are distinct entity types:
        **Users**: denoted by prefixing the name with `u/`
        **Subreddits**: denoted by prefixing the name with `r/`
        **Posts**: denoted by providing a full URL to the post.
        Additionally, a URL to a user or subreddit may be provided.
        """
        await delegate_callbacks(ctx, entity)

    @flags.add_flag(
        "-t",
        "--time",
        choices=["hour", "day", "week", "month", "year", "all"],
        default="all",
    )
    @flags.add_flag(
        "-s",
        "--sort",
        choices=["top", "new", "rising", "hot", "controversial", "best"],
        default="hot",
    )
    @flags.add_flag("-a", "--amount", type=int, default=5)
    @flags.add_flag("sub", nargs="?")
    @flags.command(name="posts")
    async def reddit_posts(ctx, **flags):
        """Get posts from a subreddit"""
        sub = await RedditConverter().convert(ctx, flags["sub"])
        async with ctx.loading(
            tick=False, exc_ignore=(KeyError, aiohttp.ContentTypeError)
        ), ctx.bot.session.get(
            f'https://www.reddit.com/r/{sub.name}/{flags["sort"]}.json',
            params={"limit": "100", "t": flags["time"]},
            allow_redirects=False,
        ) as resp:
            data = await resp.json()
        if resp.status != 200:
            raise ApiError(f"Unable to get listing [status code {resp.status}]")

        def gen_listing_embeds(listing):
            for post in listing.posts:
                yield submission_to_embed(post)

        embeds = [
            *gen_listing_embeds(
                SubListing(data, allow_nsfw=allow_nsfw_in_channel(ctx.channel))
            )
        ]
        if not embeds:
            raise ApiError(
                "Couldn't find any posts that matched the contextual criteria"
            )
        source = PagedEmbedMenu(embeds[: flags["amount"]])
        menu = CSMenu(source, clear_reactions_after=True, delete_on_button=True)
        await menu.start(ctx)


def setup(bot):
    for command in Reddit(bot).get_commands():
        bot.get_command("reddit").remove_command(command.name)
        bot.get_command("reddit").add_command(command)
