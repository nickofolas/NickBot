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
import async_cleverbot as ac
import asyncpg

import neo
import neo.context
from neo.utils.containers import Cache
from neo.config import conf, _secrets


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
        self.snipes = {}
        self.loop.create_task(self.ainit())
        self._cd = commands.CooldownMapping.from_cooldown(1.0, 2.5, commands.BucketType.user)
        self.add_check(self.global_cooldown)
        self.before_invoke(self.before)

        for ext in conf.get('exts'):
            self.load_extension(ext)

        self.run(_secrets.bot_token)

    async def ainit(self):
        self.session = aiohttp.ClientSession()
        cn = {"user": os.getenv('DBUSER'), "password": os.getenv('DBPASS'), "database": os.getenv('DB'),
              "host": os.getenv('DBHOST')}
        self.conn = await asyncpg.create_pool(
            user=_secrets.dbuser, password=_secrets.dbpass, database=_secrets.db, host=_secrets.dbhost)
        self.user_cache = await Cache(db_query="SELECT * FROM user_data",
                                      key='user_id', pool=self.conn)
        self.guild_cache = await Cache(db_query="SELECT * FROM guild_prefs",
                                   key='guild_id', pool=self.conn)

    async def get_context(self, message, *, cls=neo.context.Context):
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
                await self.user_cache.refresh() # And then updates the user cache


    # noinspection PyAttributeOutsideInit
    async def on_ready(self):
        user = self.get_user(723268667579826267)
        embed = neo.Embed(
            title='Bot is now running',
            description=textwrap.dedent(f"""
            **Name** {self.user}
            **ID** {self.user.id}
            **Guilds** {len(self.guilds)}
            **Users** {len(self.users)}
            """)).set_thumbnail(url=self.user.avatar_url_as(static_format='png'))
        embed.timestamp = datetime.utcnow()
        await user.send(embed=embed)
        self.logging_channels = {
            'guild_io': self.get_channel(710331034922647613)
        }

    async def close(self):
        [task.cancel() for task in all_tasks(loop=self.loop)]
        await self.session.close()
        await self.conn.close()
        await super().close()
