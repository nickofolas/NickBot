import difflib
import json
import os
import pprint
import re
import time
import unicodedata
from inspect import Parameter
from typing import Union, Optional
import datetime
import contextlib

import discord
import typing
import unidecode as ud
from discord.ext import commands

from utils import paginator
from utils.helpers import pluralize


def zulu_time(dt: datetime.datetime):
    return dt.isoformat()[:-6] + 'Z'


class Util(commands.Cog):
    """A variety of commands made with an emphasis
    on utility and general usefulness"""

    def __init__(self, bot):
        self.bot = bot

    @commands.group(invoke_without_command=True)
    async def snipe(self, ctx, target_channel: Union[discord.TextChannel, int] = None):
        """Retrieve the most recently deleted item from a channel
        This command can be used in 2 different ways:
            - When run with no arguments, the most recently deleted
            item from the current channel will be returned
            - If another channel is passed, then it will attempt
            to retrieve the most recently deleted item from that channel"""
        target_channel = self.bot.get_channel(target_channel) if \
            isinstance(target_channel, int) else target_channel or ctx.channel
        entries = []
        for msg, when in reversed(self.bot.snipes[target_channel.id]['deleted']):
            tup = (msg.content, msg, when)
            entries.append(tup)
        source = paginator.SnipeMenu(entries)
        menu = paginator.CSMenu(source, delete_message_after=True)
        await menu.start(ctx)

    @snipe.command(aliases=['dict'])
    @commands.is_owner()
    async def viewdict(self, ctx):
        """View the current dictionary for the snipe command"""
        send_dict = dict.fromkeys([k for k in self.bot.snipes])
        for i in self.bot.snipes:
            send_dict[i] = self.bot.snipes[i]
        await ctx.safe_send(
            ('```\n' + pprint.pformat(send_dict).replace('```', '``')
             + '\n```'))

    @snipe.command()
    async def edits(self, ctx, target_channel: Union[discord.TextChannel, int] = None):
        target_channel = self.bot.get_channel(target_channel) if \
            isinstance(target_channel, int) else target_channel or ctx.channel
        entries = []
        for before, after, when in reversed(self.bot.snipes[target_channel.id]['edited']):
            if not before.content or not after.content:
                continue
            diff = difflib.unified_diff(f'{before.content}\n'.splitlines(keepends=True),
                                 f'{after.content}\n'.splitlines(keepends=True))
            tup = ('```diff\n' + ''.join(diff) + '```', after, when)
            entries.append(tup)
        source = paginator.SnipeMenu(entries)
        menu = paginator.CSMenu(source, delete_message_after=True)
        await menu.start(ctx)

    @commands.command()
    @commands.cooldown(1, 15, commands.BucketType.user)
    async def ping(self, ctx):
        """Gets the bot's response time and latency"""
        typing_start = time.perf_counter()
        await ctx.trigger_typing()
        typing_end = time.perf_counter()
        start = time.perf_counter()
        message = await ctx.send("_ _")
        end = time.perf_counter()
        duration = (end - start) * 1000
        typing_duration = (typing_end - typing_start) * 1000
        embed = discord.Embed(
            title=' ',
            description=':ping_pong: Pong!\n'
                        f' Actual response time: {duration:.3f}ms\n'
                        f' Websocket Latency: {round(self.bot.latency * 1000, 3)}ms\n'
                        f' Typing latency: {typing_duration:.3f}ms',
            color=discord.Color.main)
        await message.edit(embed=embed)

    @commands.command(aliases=['inv'])
    async def invite(self, ctx, *, permissions=None):
        """Gets an invite link for the bot
        When run with no arguments, an invite link with
        default permissions will be returned. However, this
        command also allows for granular permission setting:
            - To request an invite link with only read_messages
            permissions, one would run `invite read_messages`"""
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

    @commands.command(aliases=['av'])
    async def avatar(self, ctx, *, target: Union[discord.Member, discord.User, int] = None):
        """Get your own, or another user's avatar
        When run with no arguments, this will return
        your avatar. You can pass a user ID or a mention
        to return the avatar of another user, who can be from
        the current guild, or anywhere."""
        target = (await self.bot.fetch_user(target)) if \
            isinstance(target, int) else target or ctx.author
        embed = discord.Embed(title=" ", description=" ", color=discord.Color.main)
        embed.set_image(url=target.avatar_url_as(static_format='png', size=4096))
        embed.set_footer(text=f"Showing avatar for: {target}")
        await ctx.send(embed=embed)

    @commands.command()
    async def playing(self, ctx, *, game):
        """Get the number of people playing a game in the server"""
        total_playing = sum(game in [a.name for a in m.activities] for m in ctx.guild.members)
        await ctx.send(embed=discord.Embed(
            title='',
            description=(
                f'{total_playing} {pluralize("member", total_playing)} are playing {game}'
            ),
            color=discord.Color.main))

    @commands.command()
    async def statuslist(self, ctx):
        """Sends all statuses neatly arranged"""
        mem = '\n'.join(sorted(
            [
                f'{ud.unidecode(m.display_name):<40}' + str(m.activity.name)
                for m in ctx.guild.members if m.activity
            ]
        ))
        await ctx.safe_send('```\n' + mem + '\n```')

    @commands.command(aliases=['charinfo'])
    async def unichar(self, ctx, *, characters: str):
        """Get information about inputted unicode characters"""

        def to_string(c):
            digit = f'{ord(c):X}'  # :X} means uppercase hex formatting
            name = unicodedata.name(c, 'Name not found.')
            return f'`\\U{digit:>08}`: ' \
                   f'[{name}](http://www.fileformat.info/info/unicode/char/' \
                   f'{digit}) - `{c}`'

        embed = discord.Embed(
            title='',
            description='\n'.join(map(to_string, characters)),
            color=discord.Color.main)
        await ctx.send(embed=embed)

    @commands.command(name='imgur')
    async def imgur(self, ctx, *, image=None):
        """Upload an image to imgur via attachment or link"""
        if image is None and not ctx.message.attachments:
            raise commands.MissingRequiredArgument(Parameter(name='image', kind=Parameter.KEYWORD_ONLY))
        image = image or await ctx.message.attachments[0].read()
        headers = {'Authorization': f"Client-ID {os.getenv('IMGUR_ID')}"}
        data = {'image': image}
        async with ctx.typing(), self.bot.session.post('https://api.imgur.com/3/image', headers=headers,
                                                       data=data) as resp:
            re = await resp.json()
            await ctx.send('<' + re['data'].get('link') + '>')

    @commands.command(name='shorten')
    async def shorten(self, ctx, *, link):
        """Shorten a link into a compact redirect"""
        resp = await self.bot.session.post('https://api.rebrandly.com/v1/links',
                                           headers={'Content-type': 'application/json',
                                                    'apikey': os.getenv('REBRANDLY_KEY')},
                                           data=json.dumps({'destination': link}))
        await ctx.send(f'Shortened URL: <https://{(await resp.json())["shortUrl"]}>')

    @commands.command()
    async def raw(self, ctx, message_id: str = None):
        """Decode the markdown of a message"""
        if message_id is None:
            async for m in ctx.channel.history(limit=2):
                if m.id == ctx.message.id:
                    continue
                else:
                    await ctx.safe_send(discord.utils.escape_markdown(m.content))
        else:
            # await ctx.message.add_reaction('<a:loading:681628799376293912>')
            converter = commands.MessageConverter()
            m = await converter.convert(ctx, message_id)
            await ctx.safe_send(discord.utils.escape_markdown(m.content))

    @commands.command(aliases=['spoll'])
    @commands.max_concurrency(1, commands.BucketType.channel)
    async def strawpoll(self, ctx, deadline_days: Optional[int] = 1, *, question):
        """
        Create a poll on Strawpoll
        - deadline_days is an optional parameter that can be passed to adjust the number of days the poll will remain active, defaults to 1 day.
        - question is a required parameter
        - After the command is run, you will be prompted to input the possible answers for the poll. Answers must be separated with a comma (`,`)
        """
        zulu_deadline = zulu_time(ctx.message.created_at + datetime.timedelta(days=deadline_days))
        answr_prompt = await ctx.send('What should the possible answers be? Separate them with `,`, or respond with '
                                      '`abort` to cancel')
        msg = await self.bot.wait_for('message', check=lambda m: m.author == ctx.author)
        await answr_prompt.delete()
        if msg.content.lower() == 'abort':
            return await ctx.send('Strawpoll creation cancelled')
        data = {"poll": {"title": question, "answers": msg.content.split(','), "has_deadline": True, "deadline": zulu_deadline, "mip": True}}
        async with self.bot.session.post('https://strawpoll.com/api/poll', data=json.dumps(data)) as resp:
            js = await resp.json()
        await ctx.send(f"Here's your poll: <https://strawpoll.com/{js.get('content_id')}>")


def setup(bot):
    bot.add_cog(Util(bot))
