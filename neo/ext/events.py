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
import asyncio
import collections
import difflib
import inspect
import logging
import re
import traceback
from contextlib import suppress
from datetime import datetime

import discord
import neo
from discord.ext import commands, tasks
from humanize import naturaltime as nt
from neo.core.context import Codeblock
from neo.utils import get_next_truck_month, rdelta_filter_null

ignored_cmds = re.compile(r"\.+")
log = logging.getLogger(__name__)


class SnipedMessage:
    def __init__(self, *, content=None, author, before=None, after=None, deleted_at):
        self.author = author
        self.deleted_at = deleted_at
        if before and after:
            diff = difflib.unified_diff(
                f"{before}\n".splitlines(keepends=True),
                f"{after}\n".splitlines(keepends=True),
            )
            self.content = "```diff\n" + "".join(diff) + "```"
        else:
            self.content = content

    def __repr__(self):
        return f"<SnipedMessage deleted_at={self.deleted_at!r} author={str(self.author)!r}>"

    def to_embed(self):
        embed = discord.Embed()
        embed.description = self.content
        embed.set_author(
            name=f"{self.author.name} - {nt(datetime.now() - self.deleted_at)}",
            icon_url=self.author.avatar_url_as(static_format="png"),
        )
        return embed


class Events(commands.Cog):
    """Contains the listeners for the bot"""

    def __init__(self, bot):
        self.bot = bot
        self.truck_month.start()

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        ignored_errors = (
            commands.CommandNotFound,
            commands.NotOwner,
            neo.utils.errors.Blacklisted,
        )
        original_error = error
        # Ignores CommandNotFound and NotOwner because they're unnecessary

        if isinstance(error, ignored_errors):
            return

        elif isinstance(error, commands.CommandOnCooldown):
            return await ctx.message.add_reaction(neo.conf["emojis"]["alarm"])
            # Handles Cooldowns uniquely

        do_emojis = True
        error = getattr(error, "original", error)
        if (settings := self.bot.user_cache.get(ctx.author.id)):
            if settings.get("repr_errors"):
                error = repr(error)
            do_emojis = settings.get("error_emojis", True)

        tb = "".join(
            traceback.format_exception(
                type(original_error), original_error, original_error.__traceback__
            )
        )
        log.error("\n" + tb)

        await self.bot.logging_channels["guild_io"].send(
            f"Invocation: {ctx.message.clean_content[:80]}\n"
            + str(Codeblock(content=tb[:1900], lang="py"))
        )

        await ctx.propagate_error(error, do_emojis=do_emojis)

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if after.content == before.content or not after.guild:
            return
        if self.bot.guild_cache[after.guild.id]["snipes"] is False:
            return
        if not self.bot.snipes.get(after.channel.id):  # Creates the snipes cache
            self.bot.snipes[after.channel.id] = {
                "deleted": collections.deque(list(), 100),
                "edited": collections.deque(list(), 100),
            }
        if usr := self.bot.user_cache.get(after.author.id):
            if not usr["can_snipe"]:
                return
        if after.content and not after.author.bot:  # Updates the snipes edit cache
            now = datetime.now()
            self.bot.snipes[after.channel.id]["edited"].append(
                SnipedMessage(
                    author=after.author,
                    before=before.content,
                    after=after.content,
                    deleted_at=now,
                )
            )

    @commands.Cog.listener("on_message_edit")
    async def process_edit_commands(self, before, after):
        if (datetime.utcnow() - before.created_at).seconds <= 600:
            if after.content != before.content:
                await self.bot.process_commands(after)

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        if not message.guild:
            return
        if self.bot.guild_cache[message.guild.id]["snipes"] is False:
            return
        if not self.bot.snipes.get(message.channel.id):  # Creates the snipes cache
            self.bot.snipes[message.channel.id] = {
                "deleted": collections.deque(list(), 100),
                "edited": collections.deque(list(), 100),
            }
        if usr := self.bot.user_cache.get(message.author.id):
            if not usr["can_snipe"]:
                return
        if (
            message.content and not message.author.bot
        ):  # Updates the snipes deleted cache
            now = datetime.now()
            self.bot.snipes[message.channel.id]["deleted"].append(
                SnipedMessage(
                    author=message.author, content=message.content, deleted_at=now
                )
            )

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        embed = discord.Embed(description=f"Joined guild {guild.name} [{guild.id}]")
        embed.set_thumbnail(url=guild.icon_url_as(static_format="png"))
        embed.add_field(
            name="**Members**",  # Basic stats about the guild
            value=f"**Total:** {len(guild.members)}\n"
            + f"**Admins:** {len([m for m in guild.members if m.guild_permissions.administrator])}\n"
            + f"**Owner: ** {guild.owner}\n",
            inline=False,
        )
        with suppress(Exception):
            async for a in guild.audit_logs(limit=5):
                # Tries to disclose who added the bot
                if a.action == discord.AuditLogAction.bot_add:
                    action = a
                    break
            embed.add_field(name="**Added By**", value=action.user)

        await self.bot.pool.execute(  # Adds/updates this guild in the db using upsert syntax
            "INSERT INTO guild_prefs (guild_id, prefixes) VALUES ($1, $2)"
            "ON CONFLICT (guild_id) DO UPDATE SET prefixes=$2",
            guild.id,
            ["n/"],
        )
        await self.bot.guild_cache.refresh()
        await self.bot.logging_channels.get("guild_io").send(embed=embed)

    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
        await self.bot.pool.execute(
            "DELETE FROM guild_prefs WHERE guild_id=$1", guild.id
        )
        # Removes guild from database
        embed = discord.Embed(
            description=f"Removed from guild {guild.name} [{guild.id}]",
            color=discord.Color.pornhub,
        )  # Don't ask
        embed.set_thumbnail(url=guild.icon_url_as(static_format="png"))
        await self.bot.guild_cache.refresh()
        await self.bot.logging_channels.get("guild_io").send(embed=embed)

    @tasks.loop(seconds=300)
    async def truck_month(self):
        next_truck_month = get_next_truck_month(datetime.now())
        next_tm = f"{', '.join(rdelta_filter_null(next_truck_month))}"
        await self.bot.change_presence(
            activity=discord.Activity(type=5, name=f"{next_tm} to truck month."),
        )

    @truck_month.before_loop
    async def wait_for_tm(self):
        await self.bot.wait_until_ready()


def setup(bot):
    bot.add_cog(Events(bot))
