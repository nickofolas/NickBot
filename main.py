import os
import warnings
from datetime import datetime
import random
from contextlib import suppress
import logging

import aiosqlite as asq
from discord.ext import commands
import discord
import aiohttp
from dotenv import load_dotenv
import async_cleverbot as ac
import asyncpg

import utils.context

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

        for filename in os.listdir('./cogs'):
            if filename.endswith('.py'):
                self.load_extension(
                    f'cogs.{filename[:-3]}')  # Load all cogs upon starting up
                self.all_cogs.append(filename[:-3].title())
            # self.load_extension('jishaku')
        TOKEN = os.getenv("TOKEN")
        self.run(TOKEN)

    async def ainit(self):
        cn = {"user": os.getenv('DBUSER'), "password": os.getenv('DBPASS'), "database": os.getenv('DB'),
              "host": os.getenv('DBHOST')}
        self.conn = await asyncpg.create_pool(**cn)

    async def get_context(self, message, *, cls=utils.context.Context):
        return await super().get_context(message, cls=cls)

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
        await self.session.close()
        await self.conn.close()
        await super().close()


NeoBot().run()
