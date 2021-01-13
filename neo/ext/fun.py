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
import io
import random
import string
import textwrap
from difflib import get_close_matches
from html import unescape as us
from typing import Union

import discord
import neo
import uwuify
from async_timeout import timeout
from discord.ext import commands
from humanize import apnumber
from PIL import Image, ImageSequence

NUM_EMOJIS = {str(num): f":{apnumber(num)}:" for num in range(10)}
IMG_MAX_SIZE = 512
GIF_MAX_SIZE = 256


def upscale(inp, is_gif=False):
    img = Image.open(io.BytesIO(inp))
    with io.BytesIO() as buffer:
        if is_gif:
            h, w = img.size
            frames = []

            while len(frames) < 100:
                ratio = GIF_MAX_SIZE / h
                frame = img.resize((GIF_MAX_SIZE, int(w * ratio)), Image.NEAREST)
                frames.append(frame)

                try:
                    img.seek(img.tell() + 1)
                except EOFError:
                    break

            frames[0].save(
                buffer,
                format="GIF",
                save_all=True,
                append_images=frames[1:],
                disposal=2,
            )
        else:
            h, w = img.size
            ratio = IMG_MAX_SIZE / h

            img = img.resize((IMG_MAX_SIZE, int(w * ratio)))
            img.save(buffer, format="PNG")
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
        await ctx.send(f"**{ctx.author.name} says: **" + " ".join(out) + "_ _")

    @commands.command()
    async def vote(self, ctx, *, poll):
        """Create an easy poll"""
        # TODO: Make the message edit itself when the reactions are updated so that it's easier to tell what the actual votes are
        embed = discord.Embed(title=" ", description=f"**Cast your vote:**\n{poll}")
        embed.set_footer(
            text=f"Vote created by {ctx.author.name}",
            icon_url=ctx.author.avatar_url_as(static_format="png"),
        )
        embed.timestamp = ctx.message.created_at
        vote = await ctx.send(embed=embed)
        await vote.add_reaction("<:upvote:655880245047459853>")
        await vote.add_reaction("<:downvote:655880259358687252>")

    @commands.command()
    async def urban(self, ctx, *, term):
        """Search urban dictionary"""
        async with self.bot.session.get(
            "http://api.urbandictionary.com/v0/define", params={"term": term}
        ) as resp:
            js = await resp.json()

        if not (defs := js["list"]):
            return await ctx.send("No results")

        menu_list = []
        for item in defs:

            entry = f"""
            **[{item['word']}]({item['permalink']})**
            \N{THUMBS UP SIGN} {item['thumbs_up']:,d} \N{THUMBS DOWN SIGN} {item['thumbs_down']:,d} 

            ***Definition:*** {item['definition']}

            **Example:**
            {item['example']}
            """
            menu_list.append(textwrap.dedent(entry))

        await ctx.paginate(
            entries=sorted(menu_list),
            per_page=1,
            delete_on_button=True,
            clear_reactions_after=True,
        )

    @commands.is_owner()
    @commands.group(name="emoji", aliases=["em"], invoke_without_command=True)
    async def get_emoji(self, ctx, *, emoji):
        ...

    @commands.max_concurrency(1, commands.BucketType.channel)
    @get_emoji.command()
    async def big(self, ctx, emoji: discord.PartialEmoji):
        """Enlarges an emoji.

        Quality of animated emojis is erratic. GIF emojis will be limited to 64 frames duration."""
        async with ctx.loading(tick=False):
            extension = "gif" if emoji.animated else "png"

            try:
                out = await self.bot.loop.run_in_executor(
                    None,
                    upscale,
                    await emoji.url.read(),
                    getattr(emoji, "animated", False),
                )

                file = discord.File(io.BytesIO(out), filename=f"largeemoji.{extension}")
                await ctx.send(f"**Requested by: **{ctx.author}", file=file)

            except discord.HTTPException as error:
                if error.code == 40005:
                    return await ctx.send(
                        "File too large to upload to Discord, aborting."
                    )

    @get_emoji.command(name="create")
    @commands.has_permissions(manage_emojis=True)
    async def create_emoji(self, ctx, name, *, image=None):
        image = (
            await (await self.bot.session.get(image)).read()
            if image
            else await ctx.message.attachments[0].read()
        )
        async with ctx.loading():
            try:
                await ctx.guild.create_custom_emoji(name=name, image=image)
            except TypeError:
                raise commands.CommandError(
                    "Couldn't find a valid image to upload in the input"
                )

    @commands.command()
    async def owoify(self, ctx, *, message):
        """uwuify some text"""
        kwargs = {}
        if len(message) < 1500:
            kwargs["flags"] = uwuify.SMILEY
        await ctx.send("**{}**: ".format(ctx.author) + uwuify.uwu(message, **kwargs))

    @commands.command(aliases=["WorldHealthOrganization"])
    async def who(self, ctx):
        """Quick minigame to try to guess who someone is from their avatar"""
        if ctx.guild.large:
            choose_from = [
                m.author
                for m in self.bot._connection._messages
                if m.guild == ctx.guild and m.author != self.bot.user
            ]
            user = random.choice(choose_from)
        else:
            user = random.choice(ctx.guild.members)
        await ctx.send(
            embed=discord.Embed().set_image(
                url=user.avatar_url_as(static_format="png", size=128)
            )
        )
        try:
            async with timeout(10):
                while True:
                    try:
                        message = await self.bot.wait_for(
                            "message",
                            timeout=10.0,
                            check=lambda m: m.author.bot is False,
                        )
                        if (
                            user.name.lower() in message.content.lower()
                            or user.display_name.lower() in message.content.lower()
                        ):
                            return await ctx.send(f"{message.author.mention} got it!")
                    except asyncio.TimeoutError:
                        continue
        except (asyncio.TimeoutError, asyncio.CancelledError):
            return await ctx.send(f"Time's up! It was {user}")

    @commands.command()
    async def dongsize(self, ctx, *, victim: discord.Member = None):
        """Go ahead. You know you want to."""
        victim = victim or ctx.author
        ran = (
            25
            if victim.id in (*self.bot.owner_ids, self.bot.user.id)
            else random.Random(victim.id).randint(1, 15)
        )
        dong = "8" + "=" * ran + "D"
        await ctx.send(dong)


def setup(bot):
    bot.add_cog(Fun(bot))
