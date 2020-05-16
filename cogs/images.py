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
import io
import random

from discord.ext import commands
from PIL import Image, ImageFont, ImageDraw
import discord


def upscale(inp):
    img = Image.open(io.BytesIO(inp))
    h, w = img.size
    for i in range(1, 10):
        if h*i > 300 or w*i > 400:
            newsize = (h*i, w*i)
            break
    try:
        img = img.resize(newsize)
    except UnboundLocalError:
        img = img.resize((h*2, w*2))
    with io.BytesIO() as out:
        img.save(out, format='PNG')
        bf = out.getvalue()
    return bf


def create_colored_image(hex_code):
    font = ImageFont.load_default()
    im = Image.new('RGB', (50, 25), f'#{hex_code}')
    draw = ImageDraw.Draw(im)
    draw.text((7.5, 7.5), hex_code.upper(), font=font, fill='#000000')
    im = im.resize((100, 50))
    with io.BytesIO() as out:
        im.save(out, format='PNG')
        bf = out.getvalue()
    return bf


class Images(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def colorgen(self, ctx, color = None):
        if color is None:
            color = "%06x" % random.randint(0, 0xFFFFFF)
        color = color.replace('#', '')
        to_send = await self.bot.loop.run_in_executor(None, create_colored_image, color)
        await ctx.send(file=discord.File(io.BytesIO(to_send), filename='color.png'))

    @commands.command()
    async def magnify(self, ctx):
        async for m in ctx.channel.history():
            try:
                if m.attachments[0].height:
                    inp = await m.attachments[0].read()
                    break
            except IndexError:
                continue
        out = await self.bot.loop.run_in_executor(None, upscale, inp)
        await ctx.send(file=discord.File(io.BytesIO(out), filename='magnified.png'))


def setup(bot):
    bot.add_cog(Images(bot))
