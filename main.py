import os
import warnings
from datetime import datetime
import random

import aiosqlite as asq
from discord.ext import commands
import discord
import aiohttp
from dotenv import load_dotenv
import async_cleverbot as ac

import utils.context

load_dotenv()


def warn(*args, **kwargs):
    pass


# Ignores deprecation warnings
warnings.warn = warn

discord.Color.pornhub = discord.Color(0xffa31a)
discord.Color.main = discord.Color(0x84cdff)


async def get_prefix(bot, message):
    prefix = 'n/'
    if not message.guild:
        return prefix
    async with asq.connect('./database.db') as db:
        async with db.execute('SELECT prefix FROM guild_prefs WHERE guild_id=?', (message.guild.id,)) as cur:
            async for r in cur:
                prefix = r[0]
        return prefix

# Bot class itself, kinda important


class NickOfOBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix=get_prefix, case_insensitive=True)
        self.session = aiohttp.ClientSession()
        self.deleted = {}
        # self.socket_stats = {}
        self.launch_time = datetime.utcnow()

        self.cleverbot = ac.Cleverbot(os.getenv("CLEVERBOT_KEY"))
        self.cleverbot.set_context(ac.DictContext(self.cleverbot))
        self.cleverbot.emotion = random.choice([
                ac.Emotion.normal, ac.Emotion.sad,
                ac.Emotion.fear, ac.Emotion.joy, ac.Emotion.anger])
        self.all_cogs = list()
        self.persistent_status = False

        for filename in os.listdir('./cogs'):
            if filename.endswith('.py'):
                self.load_extension(
                    f'cogs.{filename[:-3]}')  # Load all cogs upon starting up
                self.all_cogs.append(filename[:-3].title())

            # self.load_extension('jishaku')
        TOKEN = os.getenv("TOKEN")
        self.run(TOKEN)

    async def get_context(self, message, *, cls=utils.context.Context):
        return await super().get_context(message, cls=cls)

    async def on_ready(self):
        user = self.get_user(680835476034551925)
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name=f"{len(self.guilds):,} servers | {len(self.users):,} members"))
        embed = discord.Embed(
            title=' ', description='Bot is now online', colour=0x01f907)
        await user.send(embed=embed)

    async def close(self):
        await self.session.close()
        await self.cleverbot.close()
        await super().close()


NickOfOBot().run()
