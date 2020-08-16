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
from PIL import Image, ImageSequence
from discord.ext import commands
import uwuify
from humanize import apnumber
from async_timeout import timeout

import neo

NUM_EMOJIS = {str(num): f":{apnumber(num)}:" for num in range(10)}

def upscale(inp, is_gif=False):
    img = Image.open(io.BytesIO(inp))
    with io.BytesIO() as buffer:
        if is_gif:
            frames = []
            for frame in ImageSequence.Iterator(img):
                h, w = frame.size
                frame = frame.resize((h*2, w*2), Image.LANCZOS)
                frames.append(frame)
            frames[0].save(buffer, format='GIF', save_all=True, 
                           append_images=frames[1:], disposal=2)
        else:
            h, w = img.size
            newsize = (h*2, w*2)
            img = img.resize(newsize)
            img.save(buffer, format='PNG')
        del img
        return buffer.getvalue()


class Fun(commands.Cog):
    """Collection of fun commands"""

    def __init__(self, bot):
        self.bot = bot
        self.em_converter = commands.EmojiConverter()

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
        embed = neo.Embed(
            title=' ',
            description=f'**Cast your vote:**\n{poll}')
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
        await ctx.paginate(
            entries, per_page=1, delete_on_button=True,
            clear_reactions=True)

    async def fetch_one(self, ctx, thing: str):
        available_emojis = list(filter(
            lambda em: self.bot.guild_cache[em.guild.id]['index_emojis'] is True,
            self.bot.emojis))
        choice = get_close_matches(thing, map(lambda e: e.name, available_emojis), n=1)
        if not choice:
            raise commands.CommandError(f"Found no matches for `{thing}`")
        return await self.em_converter.convert(ctx, choice[0])

    @commands.group(name='emoji', aliases=['em'], invoke_without_command=True)
    async def get_emoji(self, ctx, *, emoji):
        """Utilise custom emoji, both animated and cross-guild in a way that normally requires nitro"""
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
    async def big(self, ctx, emoji: Union[discord.PartialEmoji, str]):
        """Enlarges an emoji. Can work on animated emojis, but results may vary in quality"""
        i = await self.fetch_one(ctx, emoji) if \
            isinstance(emoji, str) else emoji
        extension = 'gif' if i.animated else 'png'
        async with ctx.loading(tick=False):
            out = await self.bot.loop.run_in_executor(None, upscale, (await i.url.read()), i.animated)
        file = discord.File(io.BytesIO(out), filename=f'largeemoji.{extension}')
        await ctx.send(file=file, embed=neo.Embed().set_image(url=f'attachment://largeemoji.{extension}'))

    @get_emoji.command()
    async def search(self, ctx, *, query):
        """Searches the bot's indexed emojis based on the inputted query"""
        available_emojis = list(filter(
            lambda em: self.bot.guild_cache[em.guild.id]['index_emojis'] is True,
            self.bot.emojis))
        closest_matches = get_close_matches(
            query,
            map(lambda em: em.name, available_emojis),
            n=len(available_emojis))
        await ctx.paginate(
            list(map(
                lambda em: f"{em} | [{em.name}]({em.url})",
                [await self.em_converter.convert(ctx, em_name) for 
                 em_name in closest_matches])),
            10, delete_on_button=True, clear_reactions_after=True)

    @get_emoji.command(name='create')
    @commands.has_permissions(manage_emojis=True)
    async def create_emoji(self, ctx, name, *, image = None):
        image = await (await self.bot.session.get(image)).read() if image else await ctx.message.attachments[0].read()
        async with ctx.loading():
            try:
                await ctx.guild.create_custom_emoji(name=name, image=image)
            except TypeError:
                raise commands.CommandError('Couldn\'t find a valid image to upload in the input')

    @commands.command()
    async def owoify(self, ctx, *, message):
        """uwuify some text"""
        kwargs = {}
        if len(message) < 1500:
            kwargs['flags'] = uwuify.SMILEY
        await ctx.send(uwuify.uwu(message, **kwargs))

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
            embed=neo.Embed()
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
        ran = 25 if victim.id in (*self.bot.owner_ids, self.bot.user.id) else \
            random.Random(victim.id).randint(1, 15)
        dong = '8' + '='*ran + 'D'
        await ctx.safe_send(dong)


def setup(bot):
    bot.add_cog(Fun(bot))
