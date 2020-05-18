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
from utils.config import build, DictConverter

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
    prefix = 'n/'
    if not message.guild:
        return commands.when_mentioned_or(prefix)(bot, message)
    with suppress(IndexError):
        prefix = (await bot.conn.fetch('SELECT prefix FROM guild_prefs WHERE guild_id=$1', message.guild.id))[0]['prefix']
        return commands.when_mentioned_or(prefix)(bot, message)


# Bot class itself, kinda important


class NeoBot(commands.Bot):
    """The bot itself"""

    def __init__(self):
        super().__init__(command_prefix=get_prefix, case_insensitive=True,
                         allowed_mentions=discord.AllowedMentions(everyone=False, users=False, roles=False))
        self.session = aiohttp.ClientSession()
        self.snipes = {}
        self.all_cogs = list()
        self.persistent_status = False
        self.loop.create_task(self.ainit())
        self._cd = commands.CooldownMapping.from_cooldown(1.0, 2.5, commands.BucketType.user)
        self.build_config()
        self.add_check(self.global_cooldown)

        for filename in os.listdir('./cogs'):
            if filename.endswith('.py'):
                self.load_extension(
                    f'cogs.{filename[:-3]}')  # Load all cogs upon starting up
                self.all_cogs.append(filename[:-3].title())
            # self.load_extension('jishaku')
        TOKEN = os.getenv("TOKEN")
        self.run(TOKEN)

    def build_config(self):
        # noinspection PyAttributeOutsideInit
        self.CONFIG = DictConverter(dict(build()))

    async def ainit(self):
        cn = {"user": os.getenv('DBUSER'), "password": os.getenv('DBPASS'), "database": os.getenv('DB'),
              "host": os.getenv('DBHOST')}
        self.conn = await asyncpg.create_pool(**cn)

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

    async def on_ready(self):
        user = self.get_user(680835476034551925)
        embed = discord.Embed(
            title='Bot is now running',
            description=f"""
**Name** {self.user}
**ID** {self.user.id}
**Guilds** {len(self.guilds)}
**Users** {len(self.users)}
            """,
            colour=discord.Color.main).set_thumbnail(url=self.user.avatar_url_as(static_format='png'))
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


NeoBot().run()
