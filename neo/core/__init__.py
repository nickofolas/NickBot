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
import logging
import aiohttp
import asyncpg
import discord
import neo
import sys
from .config_loader import *  # noqa
from .context import Context
from contextlib import suppress
from discord.ext import commands
from neo.types import DbCache

__all__ = ("NeoBot",)

log = logging.getLogger(__name__)

discord.Color.pornhub = discord.Color(0xFFA31A)
discord.Color.main = discord.Color(0x84CDFF)

original_init = discord.Embed.__init__
def __init__(self, *args, **kwargs):
    kwargs.setdefault("colour", 0x84CDFF)
    kwargs.setdefault("color", 0x84CDFF)
    original_init(self, *args, **kwargs)

discord.Embed.__init__ = __init__

if sys.platform == "win32":
    from ctypes import windll
    windll.kernel32.SetConsoleMode(windll.kernel32.GetStdHandle(-11), 7)

LOGGERS = [("discord", logging.INFO), ("neo", logging.INFO)]

class ColouredFormatter(logging.Formatter):
    prefix = "\x1b[38;5;"
    codes = {
        "INFO": prefix + "2m",
        "WARN": prefix + "100m",
        "DEBUG": prefix + "26m",
        "ERROR": prefix + "1m",
        "WARNING": prefix + "220m",
        "_RESET": "\x1b[0m"
    }

    def format(self, record: logging.LogRecord):
        if record.levelname in self.codes:
            record.msg = self.codes[record.levelname] + str(record.msg) + self.codes["_RESET"]
            record.levelname = self.codes[record.levelname] + record.levelname + self.codes["_RESET"]
        return super().format(record)

for name, level in LOGGERS:
    log_ = logging.getLogger(name)
    handler = logging.StreamHandler()
    formatter = ColouredFormatter(
        fmt="[{asctime} {levelname}/{name}] {message}",
        style="{"
    )
    formatter.datefmt = "\x1b[38;2;132;206;255m" + "%d/%m/%Y %H:%M:%S" + formatter.codes["_RESET"]

    handler.setFormatter(formatter)
    log_.setLevel(level)
    log_.addHandler(handler)


async def get_prefix(bot, message):
    if bot.is_closed():
        return
    await bot.wait_until_ready()
    prefix = ["n/"]
    if message.guild:
        with suppress(
            KeyError
        ):  # Not sure why this *would* happen but I guess it could
            prefix = list({*bot.guild_cache[message.guild.id]["prefixes"]})
    return commands.when_mentioned_or(*prefix)(bot, message)


class NeoBot(commands.Bot):
    """The bot itself"""

    def __init__(self):
        super().__init__(
            command_prefix=get_prefix,
            case_insensitive=True,
            allowed_mentions=discord.AllowedMentions(
                everyone=False, users=False, roles=False
            ),
            intents=discord.Intents(
                **dict.fromkeys(["members", "guilds", "emojis", "presences", "messages", "reactions"], True)
            )
        )
        self.snipes = {}
        self.loop.create_task(self.__ainit__())
        self._cd = commands.CooldownMapping.from_cooldown(
            2.0, 2.5, commands.BucketType.user
        )
        self.add_check(self.global_cooldown, call_once=True)
        self.add_check(self.check_blacklist)
        self.before_invoke(self.before)

        for ext in neo.conf["exts"]:
            self.load_extension(ext)

    async def __ainit__(self):
        self.session = aiohttp.ClientSession()
        self.pool = await asyncpg.create_pool(**neo.secrets.database)
        self.user_cache = await DbCache(
            db_query="SELECT * FROM user_data", key="user_id", pool=self.pool
        )
        self.guild_cache = await DbCache(
            db_query="SELECT * FROM guild_prefs", key="guild_id", pool=self.pool
        )

    def run(self):
        super().run(neo.secrets.bot_token)

    async def get_context(self, message, *, cls=Context):
        return await super().get_context(message, cls=cls)

    def check_blacklist(self, ctx):
        if (p := self.user_cache.get(ctx.author.id)):
            if p["_blacklisted"] is True:
                raise neo.utils.errors.Blacklisted()
            else:
                return True
        else:
            return True

    async def global_cooldown(self, ctx):
        bucket = self._cd.get_bucket(ctx.message)
        retry_after = bucket.update_rate_limit()
        if retry_after and not await self.is_owner(ctx.author):
            raise commands.CommandOnCooldown(bucket, retry_after)
        return True

    async def before(self, ctx):
        if not self.user_cache.get(ctx.author.id):
            with suppress(asyncpg.exceptions.UniqueViolationError):
                await self.pool.execute("INSERT INTO user_data (user_id) VALUES ($1)", ctx.author.id)
                # Adds people to the user_data table whenever they execute their first command
                await self.user_cache.refresh()  # And then updates the user cache

    async def on_ready(self):
        log.info("Received ready event")
        self.logging_channels = {
            "guild_io": self.get_channel(neo.conf["guild_notifs_channel"])
        }

    async def close(self):  
        # wrapping all of them into a try except to let it die in peace
        with suppress(Exception):
            await self.session.close()
            await self.pool.close()
        await super().close()
        

