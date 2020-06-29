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
import string
import random
import io
import asyncio
from html import unescape as us
from typing import Union
from difflib import get_close_matches

import discord
from PIL import Image
from discord.ext import commands
import uwuify
from humanize import apnumber
from async_timeout import timeout

from neo.config import conf
from neo.utils.paginator import BareBonesMenu, CSMenu

CODE = {'A': '.-', 'B': '-...', 'C': '-.-.',
        'D': '-..', 'E': '.', 'F': '..-.',
        'G': '--.', 'H': '....', 'I': '..',
        'J': '.---', 'K': '-.-', 'L': '.-..',
        'M': '--', 'N': '-.', 'O': '---',
        'P': '.--.', 'Q': '--.-', 'R': '.-.',
        'S': '...', 'T': '-', 'U': '..-',
        'V': '...-', 'W': '.--', 'X': '-..-',
        'Y': '-.--', 'Z': '-..',

        '0': '-----', '1': '.----', '2': '..---',
        '3': '...--', '4': '....-', '5': '.....',
        '6': '-....', '7': '--...', '8': '---..',
        '9': '----.'
        }

CODE_REVERSED = {value: key for key, value in CODE.items()}

NUM_EMOJIS = {str(num): f":{apnumber(num)}:" for num in range(10)}


def to_morse(s):
    return ' '.join(CODE.get(i.upper(), i) for i in s)


def from_morse(s):
    return ''.join(CODE_REVERSED.get(i, i) for i in s.split())


def upscale(inp):
    img = Image.open(io.BytesIO(inp))
    h, w = img.size
    newsize = (h*2, w*2)
    img = img.resize(newsize)
    with io.BytesIO() as out:
        img.save(out, format='PNG')
        bf = out.getvalue()
    return bf


class Fun(commands.Cog):
    """Collection of fun commands"""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(aliases=['bin'])
    async def binary(self, ctx, *, content):
        """Convert stuff to and from binary"""
        try:
            n = int(content, 2)
            await ctx.safe_send(
                '**Converted from binary: **'
                + n.to_bytes((n.bit_length() + 7) // 8, 'big').decode())
        except Exception:
            await ctx.safe_send(str(bin(int.from_bytes(content.encode(), 'big'))))

    @commands.command()
    async def morse(self, ctx, *, message):
        """Convert a message to morse code"""
        await ctx.send(to_morse(message))

    @commands.command()
    async def demorse(self, ctx, *, morse):
        """Convert a message from morse code"""
        await ctx.send(from_morse(morse))

    @commands.command()
    @commands.cooldown(1, 15, commands.BucketType.user)
    async def emojify(self, ctx, *, message):
        """Returns the inputted message, converted to emojis"""
        out = []
        for letter in list(message):
            if letter in string.digits:
                out.append(NUM_EMOJIS[letter])
            elif letter in string.ascii_letters:
                out.append(f":regional_indicator_{letter.lower()}:")
            else:
                out.append(letter)
        await ctx.send(f'**{ctx.author.name} says: **' + ' '.join(out) + '_ _')

    @commands.command()
    async def vote(self, ctx, *, poll):
        """Create an easy poll"""
        # TODO: Make the message edit itself when the reactions are updated so that it's easier to tell what the actual votes are
        embed = discord.Embed(
            title=' ',
            description=f'**Cast your vote:**\n{poll}',
            color=discord.Color.main)
        embed.set_footer(
            text=f'Vote created by {ctx.author.name}',
            icon_url=ctx.author.avatar_url_as(static_format='png'))
        embed.timestamp = ctx.message.created_at
        vote = await ctx.send(embed=embed)
        await vote.add_reaction('<:upvote:655880245047459853>')
        await vote.add_reaction('<:downvote:655880259358687252>')

    @commands.command()
    @commands.is_nsfw()
    async def urban(self, ctx, *, term):
        """Search urban dictionary"""
        async with self.bot.session.get(
                'http://api.urbandictionary.com/v0/define',
                params={'term': term}) as resp:
            js = await resp.json()
        defs = js['list']
        menu_list = []
        for item in defs:
            menu_list.append(
                f"[Link]({item['permalink']})"
                + f"\n\n{item['definition']}\n\n**Example:**\n {item['example']}"
                .replace('[', '').replace(']', ''))
        entries = sorted(menu_list)
        source = BareBonesMenu(entries, per_page=1)
        menu = CSMenu(source, delete_message_after=True)
        await menu.start(ctx)

    async def fetch_one(self, ctx, thing: str):
        converter = commands.EmojiConverter()
        indexed_guilds = [self.bot.get_guild(k) for k, v in filter(lambda i: i[1]['index_emojis'] is True, self.bot.guild_cache.items())]
        available_emojis = list()
        for guild in indexed_guilds:
            available_emojis.extend(guild.emojis)
        choice = get_close_matches(thing, map(lambda e: e.name, available_emojis))[0]
        return await converter.convert(ctx, choice)


    @commands.group(name='emoji', aliases=['em'], invoke_without_command=True)
    async def get_emoji(self, ctx, *, emoji):
        """
        Don't have nitro? Not a problem! Use this to get some custom emoji!
        """
        await ctx.send(await self.fetch_one(ctx, emoji))

    @get_emoji.command(aliases=['r'])
    async def react(self, ctx, *, emoji):
        """
        React with emoji from other guilds without nitro!
        Use the command with an emoji name, and then add your reaction
        within 15 seconds, and the bot will remove its own.
        """
        to_react = await self.fetch_one(ctx, emoji)
        async for m in ctx.channel.history(limit=2).filter(lambda m: m.id != ctx.message.id):
            await m.add_reaction(to_react)
            important_msg = m
        try:
            react, user = await self.bot.wait_for(
                'reaction_add',
                timeout=15.0,
                check=lambda r, u:
                    r.message.id == important_msg.id and r.emoji == to_react and u.id == ctx.author.id
                    )
        except asyncio.TimeoutError:
            await important_msg.remove_reaction(to_react, self.bot.user)
        else:
            await important_msg.remove_reaction(to_react, self.bot.user)
            if ctx.channel.permissions_for(ctx.guild.me).manage_messages:
                await ctx.message.delete()

    @get_emoji.command()
    async def big(
            self, ctx,
            emoji: Union[discord.Emoji, discord.PartialEmoji, str]):
        i = await self.fetch_one(ctx, emoji) if \
            isinstance(emoji, str) else emoji
        out = await self.bot.loop.run_in_executor(None, upscale, (await i.url.read()))
        await ctx.send(file=discord.File(io.BytesIO(out), filename='largeemoji.png'))

    @get_emoji.command()
    async def view(self, ctx):
        """
        View all emoji the bot has access to
        """
        emoji_list = [e for e in self.bot.emojis]
        sorted_em = sorted(emoji_list, key=lambda e: e.name)
        entries = [f"{e} - " + e.name.replace('_', r'\_') for e in sorted_em]
        menu = CSMenu(
            BareBonesMenu(entries, per_page=25), delete_message_after=True)
        await menu.start(ctx)

    @commands.command()
    async def owoify(self, ctx, *, message):
        """uwuify some text"""
        flags = uwuify.SMILEY
        await ctx.safe_send(uwuify.uwu(message, flags=flags))

    @commands.command(aliases=['WorldHealthOrganization'])
    async def who(self, ctx):
        """Quick minigame to try to guess who someone is from their avatar"""
        if ctx.guild.large:
            choose_from = [
                m.author for m in self.bot._connection._messages if m.guild == ctx.guild and m.author != self.bot.user
            ]
            user = random.choice(choose_from)
        else:
            user = random.choice(ctx.guild.members)
        await ctx.send(
            embed=discord.Embed(color=discord.Color.main)
            .set_image(url=user.avatar_url_as(static_format='png', size=128)))
        try:
            async with timeout(10):
                while True:
                    try:
                        message = await self.bot.wait_for(
                            'message',
                            timeout=10.0,
                            check=lambda m: m.author.bot is False)
                        if user.name.lower() in message.content.lower() or user.display_name.lower() in message.content.lower():
                            return await ctx.send(f'{message.author.mention} got it!')
                    except asyncio.TimeoutError:
                        continue
        except (asyncio.TimeoutError, asyncio.CancelledError):
            return await ctx.send(f"Time's up! It was {user}")

    @commands.command()
    async def dongsize(self, ctx, *, victim: discord.Member = None):
        """Go ahead. You know you want to."""
        victim = victim or ctx.author
        ran = 25 if victim.id in (*self.bot.owner_ids, self.bot.user.id) else random.Random(victim.id).randint(1, 15)
        dong = '8' + '='*ran + 'D'
        await ctx.safe_send(dong)


def setup(bot):
    bot.add_cog(Fun(bot))
