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
import copy
import asyncio
import datetime
import json
import os
import pprint
import re
import time
import unicodedata
from inspect import Parameter
from typing import Union, Optional
from contextlib import suppress

import discord
from discord.ext import commands, flags
from async_timeout import timeout
from yarl import URL

from neo.utils import paginator
from neo.utils.converters import BetterUserConverter
from neo.utils.formatters import group, flatten
from neo.config import _secrets


def zulu_time(dt: datetime.datetime):
    return dt.isoformat()[:-6] + 'Z'

async def do_snipe_menu(ctx, snipes):
    if not snipes:
        raise commands.CommandError("Unable to snipe this channel")
    entries = [snipe.to_embed() for snipe in snipes]
    source = paginator.PagedEmbedMenu(entries)
    menu = paginator.CSMenu(source, delete_on_button=True, clear_reactions_after=True)
    await menu.start(ctx)

round_values = [1 << i for i in range(1, 13)][3:]
def constrained_round(n):
    return min(round_values, key=lambda i: abs(i-n))

class Util(commands.Cog):
    """A variety of commands made with an emphasis
    on utility and general usefulness"""

    def __init__(self, bot):
        self.bot = bot

    @flags.add_flag('target_channel', nargs='*')
    @flags.add_flag('-e', '--edits', action='store_true')
    @flags.add_flag('-a', '--all', action='store_true')
    @flags.command(name='snipe')
    async def snipe(self, ctx, **flags):
        """
        Snipe recently deleted and edited messages from a channel
        The `--all` shows both deleted and edited message, the `--edits` flag shows just edited, and no flags shows deleted
        Optionally, a target channel can be passed to snipe messages from another channel
        """
        target_channel = ctx.channel
        if tc := flags['target_channel']:
            with suppress(Exception):
                target_channel = await commands.TextChannelConverter().convert(ctx, str(tc[0]))
        try:
            if flags['all']:
                snipes = [*flatten([self.bot.snipes.get(target_channel.id)['deleted'], self.bot.snipes.get(target_channel.id)['edited']])]
            elif flags['edits']:
                snipes = self.bot.snipes.get(target_channel.id)['edited']
            else:
                snipes = self.bot.snipes.get(target_channel.id)['deleted']
        except:
            snipes = []
        (new_snipes := list(snipes)).sort(key=lambda s: s.deleted_at, reverse=True)
        await do_snipe_menu(ctx, new_snipes)

    @commands.command()
    async def ping(self, ctx):
        """Gets the bot's response time and latency"""
        start = time.perf_counter()
        message = await ctx.send(embed=discord.Embed(
            description=f':electric_plug: **Websocket** {round(self.bot.latency * 1000, 3)}ms',
            color=discord.Color.main))
        end = time.perf_counter()
        duration = (end - start) * 1000
        em = copy.copy(message.embeds[0])
        em.description += f'\n<:discord:713266471945371650> **API** {duration:.3f}ms'
        await asyncio.sleep(0.25)
        await message.edit(embed=em)

    @commands.command(aliases=['inv'])
    async def invite(self, ctx, *, permissions=None):
        """Gets an invite link for the bot"""
        if permissions:
            try:
                p = int(permissions)
                permissions = discord.Permissions(p)
            except ValueError:
                permission_names = tuple(re.split(r'[ ,] ?', permissions))
                permissions = discord.Permissions()
                permissions.update(**dict.fromkeys(permission_names, True))
        else:
            permissions = discord.Permissions(1878523719)
        invite_url = discord.utils.oauth_url(self.bot.user.id, permissions)
        embed = discord.Embed(
            title='Invite me to your server!',
            description=f'[`Invite Link`]({invite_url})\n**Permissions Value** {permissions.value}',
            color=discord.Color.main
        ).set_thumbnail(url=self.bot.user.avatar_url_as(static_format='png'))
        await ctx.send(embed=embed)

    @flags.add_flag('target', nargs='?')
    @flags.add_flag('-s', '--size', nargs='?', type=int, default=4096)
    @flags.add_flag('-f', '--format', nargs='?')
    @flags.command(aliases=['av'])
    async def avatar(self, ctx, **flags):
        """Get your own, or another user's avatar"""
        target = (await BetterUserConverter().convert(ctx, flags.get('target'))).obj
        new_size = constrained_round(flags['size'])
        formats = ['png', 'jpeg', 'webp', 'jpg']
        if f := flags.get('format'):
            main_format = f
        if target.is_avatar_animated(): 
            formats.append('gif')
            main_format = 'gif'
        else:
            main_format = 'png'
        embed = discord.Embed(color=discord.Color.main)
        embed.set_image(url=(aurl := target.avatar_url_as(format=main_format, size=new_size)))
        embed.description = ' | '.join(f"[{fmt.upper()}]({target.avatar_url_as(format=fmt, size=new_size)})" for fmt in formats)
        actual_size = URL(str(aurl)).query.get('size', new_size)
        embed.set_footer(text=f"{target} | {actual_size}x{actual_size} px")
        await ctx.send(embed=embed)

    @commands.command(aliases=['charinfo'])
    async def unichar(self, ctx, *, characters: str):
        """Get information about inputted unicode characters"""

        def to_string(c):
            digit = f'{ord(c):X}'  # :X} means uppercase hex formatting
            name = unicodedata.name(c, 'Name not found.')
            return f'`\\U{digit:>08}` | `{c}` | ' \
                   f'[{name}](http://www.fileformat.info/info/unicode/char/' \
                   f'{digit})'
        chars = [*map(to_string, characters)]
        await ctx.quick_menu(chars, 10, delete_on_button=True, clear_reactions_after=True)

    @commands.command(name='imgur')
    @commands.max_concurrency(1, commands.BucketType.channel)
    async def imgur(self, ctx, *, image=None):
        """Upload an image to imgur via attachment or link"""
        if image is None and not ctx.message.attachments:
            raise commands.MissingRequiredArgument(Parameter(name='image', kind=Parameter.KEYWORD_ONLY))
        image = image or await ctx.message.attachments[0].read()
        headers = {'Authorization': f"Client-ID {_secrets.imgur_id}"}
        data = {'image': image}
        async with ctx.loading(), self.bot.session.post('https://api.imgur.com/3/image',
                                                        headers=headers, data=data) as resp:
            res = await resp.json()
            if link := res['data'].get('link'):
                await ctx.send('<' + link + '>')
            else:
                raise commands.CommandError('There was a problem uploading that!')

    @commands.command(name='shorten')
    async def shorten(self, ctx, *, link):
        """Shorten a link into a compact redirect"""
        resp = await self.bot.session.post('https://api.rebrandly.com/v1/links',
                                           headers={'Content-type': 'application/json',
                                                    'apikey': _secrets.rebrandly_key},
                                           data=json.dumps({'destination': link}))
        if url := (await resp.json())["shortUrl"]:
            await ctx.send(f'Shortened URL: <https://{url}>')

    @commands.command(name='ocr')
    @commands.max_concurrency(1, commands.BucketType.channel)
    async def _ocr_command(self, ctx, *, image_url: str = None):
        """Run an image through Optical Character Recognition (OCR) and return any detected text"""
        if image_url is None and not ctx.message.attachments:
            raise commands.MissingRequiredArgument(Parameter(name='image', kind=Parameter.KEYWORD_ONLY))
        image = image_url or ctx.message.attachments[0].url
        async with timeout(30), ctx.loading(tick=False), self.bot.session.get('https://api.tsu.sh/google/ocr', params={'q': image}) as resp:
            output = (await resp.json()).get('text', 'No result')
        await ctx.quick_menu(group(output, 750), 1, delete_on_button=True, clear_reactions_after=True)


def setup(bot):
    bot.add_cog(Util(bot))
