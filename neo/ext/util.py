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
import asyncio
import datetime
import json
import re
import time
import unicodedata
import random
from inspect import Parameter
from typing import Union, Optional
from contextlib import suppress
from collections import Counter

import discord
from discord.ext import commands, flags
from async_timeout import timeout
from yarl import URL

import neo
from neo.utils import paginator
from neo.utils.converters import BetterUserConverter
from neo.utils.formatters import group, flatten
from neo.utils.checks import snipe_check

imgur_media_base = URL.build(scheme='http', host='imgur.com')

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

    @flags.add_flag('target_channel', nargs='?', type=int)
    @flags.add_flag('-e', '--edits', action='store_true')
    @flags.add_flag('-a', '--all', action='store_true')
    @snipe_check()
    @flags.command(name='snipe')
    async def snipe(self, ctx, **flags):
        """
        Snipe recently deleted and edited messages from a channel
        The `--all` shows both deleted and edited message, the `--edits` flag shows just edited, and no flags shows deleted
        Optionally, a target channel ID can be passed to snipe messages from another channel
        """
        target_channel = ctx.channel.id
        if tc := flags['target_channel']:
            target_channel = tc
        try:
            if flags['all']:
                snipes = [*flatten(
                    [self.bot.snipes.get(target_channel)['deleted'],
                     self.bot.snipes.get(target_channel)['edited']])]
            elif flags['edits']:
                snipes = self.bot.snipes.get(target_channel)['edited']
            else:
                snipes = self.bot.snipes.get(target_channel)['deleted']
        except:
            snipes = []
        (new_snipes := list(snipes)).sort(key=lambda s: s.deleted_at, reverse=True)
        await do_snipe_menu(ctx, new_snipes)

    @commands.command()
    async def ping(self, ctx):
        """Gets the bot's response time and latency"""
        start = time.perf_counter()
        message = await ctx.send(embed=neo.Embed(
            description=f':electric_plug: **Websocket** {round(self.bot.latency * 1000, 3)}ms'))
        end = time.perf_counter()
        duration = (end - start) * 1000
        em = message.embeds[0].copy()
        em.description += f'\n{neo.conf["emojis"]["discordlogo"]} **API** {duration:.3f}ms'
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
        embed = neo.Embed(
            title='Invite me to your server!',
            description=f'[`Invite Link`]({invite_url})\n**Permissions Value** {permissions.value}'
        ).set_thumbnail(url=self.bot.user.avatar_url_as(static_format='png'))
        await ctx.send(embed=embed)

    @flags.add_flag('target', nargs='?')
    @flags.add_flag('-s', '--size', nargs='?', type=int, default=4096)
    @flags.add_flag('-f', '--format', nargs='?')
    @flags.command(aliases=['av'])
    async def avatar(self, ctx, **flags):
        """Get your own, or another user's avatar"""
        target = await BetterUserConverter().convert(ctx, flags.get('target'))
        new_size = constrained_round(flags['size'])
        formats = ['png', 'jpeg', 'webp', 'jpg']
        if f := flags.get('format'):
            main_format = f
        if target.is_avatar_animated(): 
            formats.append('gif')
            main_format = 'gif'
        else:
            main_format = 'png'
        (embed := neo.Embed()).set_image(url=(aurl := target.avatar_url_as(
            format=main_format, size=new_size)))
        embed.description = ' | '.join(
            f"[{fmt.upper()}]({target.avatar_url_as(format=fmt, size=new_size)})"
            for fmt in formats)
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
        headers = {'Authorization': f"Client-ID {neo.secrets.imgur_id}"}
        data = {'image': image}
        async with ctx.loading(), self.bot.session.post('https://api.imgur.com/3/image',
                                                        headers=headers, data=data) as resp:
            res = await resp.json()
            if (link := res['data'].get('link')) and (social := res['data'].get('id')):
                await ctx.send(f"Image URL: <{link}>\nSocial URL: <{imgur_media_base.with_path(social)}>")
            else:
                raise commands.CommandError('There was a problem uploading that!')

    @commands.command(name='shorten')
    async def shorten(self, ctx, *, link):
        """Shorten a link into a compact redirect"""
        resp = await self.bot.session.post('https://api.rebrandly.com/v1/links',
                                           headers={'Content-type': 'application/json',
                                                    'apikey': neo.secrets.rebrandly_key},
                                           data=json.dumps({'destination': link}))
        if url := (await resp.json()).get("shortUrl"):
            await ctx.send(f'Shortened URL: <https://{url}>')
        else:
            raise commands.CommandError('Couldn\'t shorten your link')

    @commands.command(name='ocr')
    @commands.max_concurrency(1, commands.BucketType.channel)
    async def _ocr_command(self, ctx, *, image_url: str = None):
        """Run an image through Optical Character Recognition (OCR) and return any detected text"""
        if image_url is None and not ctx.message.attachments:
            raise commands.MissingRequiredArgument(Parameter(name='image', kind=Parameter.KEYWORD_ONLY))
        image = image_url or ctx.message.attachments[0].url
        async with timeout(30), \
                ctx.loading(tick=False), \
                self.bot.session.get(
                    'https://api.tsu.sh/google/ocr',
                    params={'q': image}) as resp:
            output = (await resp.json()).get('text', 'No result')
        await ctx.quick_menu(group(output, 750) or ['No result'], 1, delete_on_button=True, clear_reactions_after=True)

    @commands.group(name='choose', invoke_without_command=True)
    async def random_choice(self, ctx, *options):
        """Choose between multiple choices"""
        if len(options) < 2:
            raise commands.CommandError('Not enough choices provided')
        await ctx.send(random.choice(options))

    @random_choice.command(name='best')
    async def random_choice_bestof(self, ctx, times: Optional[int], *options):
        """Choose between multiple choices `times` times"""
        if len(options) < 2:
            raise commands.CommandError('Not enough choices provided')
        times = min(10001, max(1, times or ((len(options) ** 2) + 1)))
        choices = Counter(random.choice(options) for _ in range(times))
        choices = sorted(choices.items(), key=lambda i: i[1], reverse=True)
        formatted_choices = (f'{c}. `{choice.ljust(len(max(options, key=len)))}` '
                             f'[{amt} | {amt/times * 100:.1f}%]' for 
                             c, (choice, amt) in enumerate(choices, 1))
        await ctx.send('\n'.join(formatted_choices))

def setup(bot):
    bot.add_cog(Util(bot))
