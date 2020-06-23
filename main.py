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
import os
import textwrap
import warnings
from datetime import datetime
from asyncio import all_tasks
from contextlib import suppress
import logging

from discord.ext import commands
import discord
import aiohttp
from dotenv import load_dotenv
import async_cleverbot as ac
import asyncpg

import utils.context
from utils.containers import Cache
from config import conf

load_dotenv()


def warn(*args, **kwargs):
    pass


logging.basicConfig(level=logging.INFO)

# Ignores deprecation warnings
warnings.warn = warn

# noinspection SpellCheckingInspection
discord.Color.pornhub = discord.Color(0xffa31a)
discord.Color.main = discord.Color(0x84cdff)

async def get_prefix(bot, message):
    if bot.is_closed():
        return
    await bot.wait_until_ready()
    prefix = 'n/'
    if message.guild:
        with suppress(KeyError):
            prefix = bot.guild_cache[message.guild.id]['prefix']
    return commands.when_mentioned_or(prefix)(bot, message)


# Bot class itself, kinda important


class NeoBot(commands.Bot):
    """The bot itself"""

    def __init__(self):
        super().__init__(command_prefix=get_prefix, case_insensitive=True,
                         allowed_mentions=discord.AllowedMentions(everyone=False, users=False, roles=False))
        self.session = aiohttp.ClientSession()
        self.snipes = {}
        self.loop.create_task(self.ainit())
        self._cd = commands.CooldownMapping.from_cooldown(1.0, 2.5, commands.BucketType.user)
        self.add_check(self.global_cooldown)
        self.user_cache = dict()
        self.guild_cache = dict() 
        self.before_invoke(self.before)

        for ext in conf.get('exts'):
            self.load_extension(ext)

        TOKEN = os.getenv("TOKEN")
        self.run(TOKEN)

    async def ainit(self):
        cn = {"user": os.getenv('DBUSER'), "password": os.getenv('DBPASS'), "database": os.getenv('DB'),
              "host": os.getenv('DBHOST')}
        self.conn = await asyncpg.create_pool(**cn)
        self.guild_cache_2 = Cache(db_query="SELECT * FROM guild_prefs",
                                   key='guild_id', loop=self.loop, pool=self.conn)

    async def get_context(self, message, *, cls=utils.context.Context):
        return await super().get_context(message, cls=cls)

    async def global_cooldown(self, ctx):
        if ctx.invoked_with == self.help_command.command_attrs.get('name', 'help'):
            return True
        bucket = self._cd.get_bucket(ctx.message)
        retry_after = bucket.update_rate_limit()
        if retry_after:
            raise commands.CommandOnCooldown(bucket, retry_after)
        return True

    async def before(self, ctx):
        if not self.user_cache.get(ctx.author.id):
            with suppress(asyncpg.exceptions.UniqueViolationError):
                await self.conn.execute('INSERT INTO user_data (user_id) VALUES ($1)', ctx.author.id)
                # Adds people to the user_data table whenever they execute their first command
                await self.build_user_cache() # And then updates the user cache


    # noinspection PyAttributeOutsideInit
    async def on_ready(self):
        user = self.get_user(723268667579826267)
        embed = discord.Embed(
            title='Bot is now running',
            description=textwrap.dedent(f"""
            **Name** {self.user}
            **ID** {self.user.id}
            **Guilds** {len(self.guilds)}
            **Users** {len(self.users)}
            """),
            colour=discord.Color.main).set_thumbnail(url=self.user.avatar_url_as(static_format='png'))
        embed.timestamp = datetime.utcnow()
        await user.send(embed=embed)
        self.logging_channels = {
            'guild_io': self.get_channel(710331034922647613)
        }
        await self.build_user_cache()
        await self.build_guild_cache()

    async def build_user_cache(self):
        self.user_cache.clear()
        for record in await self.conn.fetch("SELECT * FROM user_data"):
            user = dict(record)
            self.user_cache[user.pop('user_id')] = user

    async def build_guild_cache(self):
        self.guild_cache.clear()
        for record in await self.conn.fetch("SELECT * FROM guild_prefs"):
            guild = dict(record)
            self.guild_cache[guild.pop('guild_id')] = guild

    async def close(self):
        [task.cancel() for task in all_tasks(loop=self.loop)]
        await self.session.close()
        await self.conn.close()
        await super().close()


NeoBot().run()
