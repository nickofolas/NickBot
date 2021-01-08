"""
neo Discord bot
Copyright (C) 2021 nickofolas

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
import argparse
import asyncio
import collections
import re
import shlex
import textwrap
from contextlib import suppress
from types import SimpleNamespace
from typing import Union

import discord
from discord.ext import commands, flags, tasks
from discord.ext.commands import has_permissions
from neo.utils.checks import is_owner_or_administrator
from neo.utils.converters import BoolConverter
from neo.utils.formatters import prettify_text

custom_emoji = re.compile(
    r"(<a?:\w*:\d*>)|([\U00002600-\U000027BF])|([\U0001f300-\U0001f64F])|([\U0001f680-\U0001f6FF])"
)


class Guild(commands.Cog):
    """Everything to do with guild management can be found here"""

    def __init__(self, bot):
        self.bot = bot
        self._counting_cache = collections.defaultdict(dict)
        self._cache_ready = False
        self.locks = {}
        bot.loop.create_task(self.get_cache())

    async def get_cache(self):
        await self.bot.wait_until_ready()
        for record in await self.bot.pool.fetch(
            "SELECT guild_id, counting_channel FROM guild_prefs"
        ):
            _id, counting = record
            if not counting:
                continue
            self._counting_cache[_id] = dict(counting)
            self.locks[_id] = asyncio.Lock()
        if not self._cache_ready:
            self.push_counting_data.start()
            self._cache_ready = True

    def cog_check(self, ctx):
        return bool(ctx.guild)

    @flags.add_flag("search_depth", type=int, nargs="?", default=5)
    @flags.add_flag("--user", nargs="+")
    @flags.add_flag("--contains", nargs="+")
    @flags.add_flag("--or", action="store_true", dest="_or")
    @flags.add_flag("--not", action="store_true", dest="_not")
    @flags.add_flag("--bot", action="store_const", const=lambda m: m.author.bot)
    @flags.add_flag("--after", type=int, default=0)
    @flags.add_flag("--before", type=int, default=0)
    @has_permissions(manage_messages=True)
    @commands.max_concurrency(1, commands.BucketType.channel)
    @flags.command(name="clear", aliases=["c"])
    async def custom(self, ctx, **args):
        """Clear messages from the channel"""
        predicates = []

        if args["bot"]:
            predicates.append(args["bot"])

        if args["user"]:
            users = []
            converter = commands.MemberConverter()
            for u in args["user"]:
                with suppress(Exception):
                    user = await converter.convert(ctx, u)
                    users.append(user)
            predicates.append(lambda m: m.author in users)

        if args["contains"]:
            predicates.append(
                lambda m: any(sub in m.content for sub in args["contains"])
            )

        op = all if not args["_or"] else any
        def predicate(m):
            r = op(p(m) for p in predicates)
            if args["_not"]:
                return not r

            return r

        constraints = {"before": discord.Object(args["before"] or ctx.message.id)}
        if args["after"]:
            constraints.update(after=discord.Object(args["after"]))

        args["search_depth"] = max(
            0, min(2000, args["search_depth"])
        )  # clamp from 0-2000
        async with ctx.loading(tick=False):
            deleted = await ctx.channel.purge(
                limit=args["search_depth"], check=predicate, **constraints
            )
        
        await ctx.message.delete()
        await ctx.send(f"{len(deleted)} messages purged.", delete_after=5)

    @commands.command()
    @has_permissions(ban_members=True)
    async def ban(self, ctx, member: Union[discord.Member, int], *, reason=None):
        """Issue a ban, can use the ID of a member outside the guild to hackban them"""
        user_obj = (
            await self.bot.fetch_user(member) if isinstance(member, int) else member
        )
        await ctx.guild.ban(
            user_obj, reason=f"{ctx.author} ({ctx.author.id}) - {reason}"
        )
        await ctx.send(f"Banned **{user_obj}**")

    @commands.command()
    @has_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member, *, reason=None):
        """Kick a member - optional reason can be provided"""
        await member.kick(reason=f"{ctx.author} ({ctx.author.id}) - {reason}")
        await ctx.send(f"Kicked **{member}**")

    @commands.group(name="counting", invoke_without_command=True)
    async def _guild_counting(self, ctx):
        if (_counting := self._counting_cache[ctx.guild.id]) is None:
            return
        embed = discord.Embed(title="Counting")
        embed.description = textwrap.dedent(
            f"""
        **Current Number** {_counting["current_number"]:,d}
        **Channel** <#{_counting["channel_id"]}>
        """
        )
        await ctx.send(embed=embed)

    @is_owner_or_administrator()
    @_guild_counting.command(name="channel")
    async def _guild_counting_channel(self, ctx, channel: discord.TextChannel = None):
        if self._counting_cache.get(ctx.guild.id) is None:
            await self.bot.pool.execute(
                "UPDATE guild_prefs SET counting_channel=$1::counting WHERE guild_id=$2",
                {
                    "channel_id": channel.id,
                    "current_number": 0,
                },
                ctx.guild.id,
            )

            await self.get_cache()
            return await ctx.send(
                "Counting channel configured and bound to {.mention}".format(channel)
            )

        channel = getattr(channel, "id", 0)
        await self.bot.pool.execute(
            "UPDATE guild_prefs SET counting_channel.channel_id=$1 WHERE guild_id=$2",
            channel,
            ctx.guild.id,
        )

        await self.get_cache()
        await ctx.message.add_reaction(ctx.tick(True))

    @is_owner_or_administrator()
    @_guild_counting.command(name="number")
    async def _guild_counting_number_override(self, ctx, number: int):
        if self._counting_cache.get(ctx.guild.id) is None:
            return await ctx.send("You must first set up a channel!")

        await self.bot.pool.execute(
            "UPDATE guild_prefs SET counting_channel.current_number=$1 WHERE guild_id=$2",
            number,
            ctx.guild.id,
        )
        await self.get_cache()

        await ctx.message.add_reaction(ctx.tick(True))

    @commands.Cog.listener(name="on_message")
    async def check_counting(self, msg):
        if not msg.guild:
            return
        elif not self._counting_cache.get(msg.guild.id):
            return
        elif self._counting_cache[msg.guild.id]["channel_id"] != msg.channel.id:
            return
        lock = self.locks[msg.guild.id]
        try:
            if lock.locked():
                raise ValueError()
            async with lock:
                new = int(msg.content)
                cur = self._counting_cache[msg.guild.id]["current_number"]
                if new == (cur + 1):
                    self._counting_cache[msg.guild.id]["current_number"] = new
                    return
                else:
                    raise ValueError()
        except ValueError:
            await msg.delete()

    @commands.Cog.listener("on_message_edit")
    async def handle_edited_message(self, before, after):
        if not after.guild:
            return
        if not (
            current_value := self._counting_cache[before.guild.id].get("current_number")
        ):
            return
        if after.id != after.channel.last_message_id:
            return

        if self._counting_cache[after.guild.id]["channel_id"] == after.channel.id:
            await after.delete()
            original_value = int(before.content)
            if current_value == original_value:
                self._counting_cache[after.guild.id]["current_number"] -= 1

    @tasks.loop(seconds=300)
    async def push_counting_data(self):
        for _id, data in self._counting_cache.items():
            await self.bot.pool.execute(
                "UPDATE guild_prefs SET counting_channel=$1::counting WHERE guild_id=$2",
                data,
                _id,
            )

    @push_counting_data.before_loop
    async def wait_for_ready(self):
        await self.bot.wait_until_ready()

    @push_counting_data.after_loop
    async def push_final_data(self):
        for _id, data in self._counting_cache.items():
            await self.bot.pool.execute(
                "UPDATE guild_prefs SET counting_channel=$1::counting WHERE guild_id=$2",
                data,
                _id,
            )

    def cog_unload(self):
        self.push_counting_data.cancel()


def setup(bot):
    bot.add_cog(Guild(bot))
