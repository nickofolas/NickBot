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
import re
import asyncio
from collections import namedtuple
from contextlib import suppress
from textwrap import shorten as shn

import discord
from discord.ext import commands, flags, tasks

from utils.checks import check_member_in_guild
from config import conf
from utils.containers import TimedSet

# Constants
MAX_HIGHLIGHTS = 10
PendingHighlight = namedtuple('PendingHighlight', ['user', 'embed'])

regex_flag = re.compile(r"--?re(gex)?")
regex_check = re.compile(r"(?P<charmatching>(\.|\\w|\\S|\\D)(\)*)?[\*\+]|\[(a-z)?(A-­Z)?(0-9)?(_)?])|(?P<or>(\|.*){5})")


class Highlight:
    def __init__(self, user_id, kw, is_regex = True):
        self.user_id = user_id
        self.kw = kw
        self.is_regex = is_regex
        self.compiled = re.compile(fr"\b{re.escape(kw)}\b", re.I)
        if is_regex:
            try:
                self.compiled = re.compile(kw, re.I)
            except re.error:
                self.is_regex = False

    def __repr__(self):
        attrs = ' '.join(f"{k}={v!r}" for k, v in self.__dict__.items())
        return f"<{self.__class__.__name__} {attrs}>"

    def check_can_send(self, message, bot):
        predicates = []
        if not message.guild:
            return False
        if self.user_id not in [m.id for m in message.guild.members]:
            return False
        predicates.append(not re.search(re.compile(r'([a-zA-Z0-9]{24}\.[a-zA-Z0-9]{6}\.[a-zA-Z0-9_\-]{27}|mfa\.['
                                                   r'a-zA-Z0-9_\-]{84})'), message.content))
        if wl := bot.user_cache[self.user_id]['hl_whitelist']:
            predicates.append(message.guild.id in wl)
        if blocks := bot.user_cache[self.user_id]['hl_blocks']:
            predicates.extend([message.author.id not in blocks, message.guild.id not in blocks])
        predicates.extend([self.user_id != message.author.id,
                           message.channel.permissions_for(
                               message.guild.get_member(self.user_id)).read_messages is not False,
                           not message.author.bot])
        return all(predicates)

    @staticmethod
    async def to_embed(match, message):
        context_list = []
        async for m in message.channel.history(limit=5):
            avatar_index = m.author.default_avatar.value
            hl_underline = m.content.replace(match, f'**__{match}__**') if m.id == message.id else m.content
            repl = r'<a?:\w*:\d*>'
            context_list.append(
                f"{conf['default_discord_users'][avatar_index]} **{m.author.name}:** "
                f"{re.sub(repl, ':question:', hl_underline)}")
        context_list.reverse()
        while len('\n'.join(context_list)) > 2048:
            context_list = context_list[1:]
        embed = discord.Embed(
            title=f'Highlighted in {message.guild.name}/#{message.channel.name} with "{shn(match, width=25)}"',
            description='\n'.join(context_list) + f'\n[Jump URL]({message.jump_url})',
            color=discord.Color.main)
        embed.timestamp = message.created_at
        return embed


class HlMon(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.cache = []
        self.queue = []
        self.recents = {}
        bot.loop.create_task(self.update_highlight_cache())
        self.do_highlights.start()

    def cog_unload(self):
        self.do_highlights.cancel()

    @commands.Cog.listener(name='on_message')
    async def watch_highlights(self, msg):
        for hl in self.cache:
            if hl.user_id in self.recents.get(msg.channel.id, {}):
                continue
            match = None
            if m := hl.compiled.search(msg.content):
                match = m.group(0)
            if match is None or hl.check_can_send(msg, self.bot) is False:
                continue
            if len(self.queue) < 40 and self.queue.count(hl.user_id) < 5:
                self.queue.append(PendingHighlight(self.bot.get_user(hl.user_id), (await hl.to_embed(match, msg))))

    @commands.Cog.listener(name='on_message')
    async def update_recents(self, msg):
        if msg.author.id in {hl.user_id for hl in self.cache}:
            if not self.recents.get(msg.channel.id):
                self.recents.update({msg.channel.id: TimedSet(decay_time=60, loop=self.bot.loop)})
            self.recents[msg.channel.id].add(msg.author.id)

    @commands.Cog.listener(name='on_hl_update')
    async def update_highlight_cache(self):
        await self.bot.wait_until_ready()
        self.cache = [Highlight(**dict(record)) for record in await self.bot.conn.fetch("SELECT * FROM highlights")]

    @tasks.loop(seconds=10)
    async def do_highlights(self):
        try:
            for pending in set(self.queue):
                with suppress(Exception):
                    await pending.user.send(embed=pending.embed)
                    await asyncio.sleep(0.25)
        finally:
            self.queue.clear()

    @do_highlights.before_loop
    async def wait_for_ready(self):
        await self.bot.wait_until_ready()


def index_check(command_input):
    try:
        int(command_input[0])
    except ValueError:
        return False
    return True


def check_regex(kw):
    if s := regex_check.search(kw):
        d = s.groupdict()
        raise commands.CommandError(f"Disallowed regex character(s) {set(i for i in d.values() if i)}")

def guild_or_user(bot, snowflake_id):
    return f'**User** {bot.get_user(snowflake_id)}' if bot.get_user(snowflake_id) else f'**Guild** {bot.get_guild(snowflake_id)}'

strategies = {'block': 'array_append', 'unblock': 'array_remove'}

# noinspection PyMethodParameters
class HighlightCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(usage="<highlight> [--regex]")
    async def add(ctx):
        """
        Add a new highlight! When a highlighted word is used, you'll get notified!
        If the --regex flag is passed, the highlight will be compiled as a regex
        """
        highlight_words = regex_flag.sub('', re.sub(fr"{ctx.prefix}h(igh)?l(ight)? add", '', ctx.message.content)).strip()
        with_regex = bool(regex_flag.search(ctx.message.content))
        if with_regex:
            check_regex(highlight_words)
        if len(highlight_words) < 3:
            raise commands.CommandError('Highlights must be more than 2 characters long')
        active = await ctx.bot.conn.fetch('SELECT kw FROM highlights WHERE user_id=$1', ctx.author.id)
        if len(active) >= MAX_HIGHLIGHTS:
            raise commands.CommandError(f'You may only have {MAX_HIGHLIGHTS} highlights at a time')
        if highlight_words in [rec['kw'] for rec in active]:
            raise commands.CommandError('You already have a highlight with this trigger')
        await ctx.bot.conn.execute(
            'INSERT INTO highlights(user_id, kw, is_regex) VALUES ( $1, $2, $3 )',
            ctx.author.id, fr"{highlight_words}", with_regex)
        ctx.bot.dispatch('hl_update')
        await ctx.message.add_reaction(ctx.tick(True))

    @commands.command(name='block', aliases=['unblock'])
    async def hl_block(ctx, user_or_guild = None):
        """Block and unblock users and guilds"""
        if not user_or_guild:
            if b := ctx.bot.user_cache[ctx.author.id]['hl_blocks']:
                blocked = [f"{guild_or_user(ctx.bot, i)} ({i})" for i in b]
            else:
                blocked = ["No blocked users or guilds"]
            await ctx.quick_menu(blocked, 10, delete_message_after=True)
            return
        strategy = strategies.get(ctx.subcommand_passed)
        snowflake = user_or_guild
        try:
            blocked = (await commands.UserConverter().convert(ctx, snowflake)).id
        except:
            blocked = int(snowflake)
        async with ctx.loading():
            await ctx.bot.conn.execute(f"UPDATE user_data SET hl_blocks = {strategy}(hl_blocks, $1) WHERE "
                                       "user_id=$2", blocked, ctx.author.id)
            await ctx.bot.user_cache.refresh()

    @flags.add_flag('-a', '--add', nargs='*')
    @flags.add_flag('-r', '--remove', nargs='*')
    @commands.command(name='whitelist', aliases=['wl'], cls=flags.FlagCommand)
    async def hl_whitelist(ctx, **flags):
        """Whitelist a guild for highlighting
        This will restrict highlights to only be allowed from guilds on the list"""
        if not flags.get('add') and not flags.get('remove'):
            if b := ctx.bot.user_cache[ctx.author.id]['hl_whitelist']:
                whitelisted = [f"{ctx.bot.get_guild(i)} ({i})" for i in b]
            else:
                whitelisted = ["Highlight guild whitelist is empty"]
            await ctx.quick_menu(whitelisted, 10, delete_message_after=True)
            return
        strategy = 'array_append' if flags.get('add') else 'array_remove'
        snowflake = (flags.get('add') or flags.get('remove'))[0]
        async with ctx.loading():
            await ctx.bot.conn.execute(f"UPDATE user_data SET hl_whitelist = {strategy}(hl_whitelist, $1) WHERE "
                                       "user_id=$2", int(snowflake), ctx.author.id)
            await ctx.bot.user_cache.refresh()

    @commands.command(name='remove', aliases=['rm', 'delete', 'del', 'yeet'])
    async def remove_highlight(ctx, highlight_index: commands.Greedy[int]):
        """
        Remove one, or multiple highlights by index
        """
        if not highlight_index:
            raise commands.CommandError('Use the index of a highlight (found in your list of highlights) to remove it')
        fetched = [rec['kw'] for rec in
                   await ctx.bot.conn.fetch("SELECT kw from highlights WHERE user_id=$1", ctx.author.id)]
        for num in highlight_index:
            await ctx.bot.conn.execute('DELETE FROM highlights WHERE user_id=$1 AND kw=$2',
                                       ctx.author.id, fetched[num - 1])
        ctx.bot.dispatch('hl_update')
        await ctx.message.add_reaction(ctx.tick(True))

    @commands.command(name='clear', aliases=['yeetall'])
    async def clear_highlights(ctx):
        """
        Completely wipe your list of highlights
        """
        confirm = await ctx.prompt('Are you sure you want to clear all highlights?')
        if confirm:
            await ctx.bot.conn.execute('DELETE FROM highlights WHERE user_id=$1', ctx.author.id)
            ctx.bot.dispatch('hl_update')

    @commands.command(name='import')
    @check_member_in_guild(292212176494657536)
    @commands.max_concurrency(1, commands.BucketType.channel)
    async def import_from_highlight(ctx):
        """
        Import your highlights from the <@292212176494657536> bot (can only be run in shared guilds)
        Imports every highlight it can while maintaining the maximum number of slots.
        """
        await ctx.send('Please call your lists of highlights from <@292212176494657536>')
        msg = await ctx.bot.wait_for('message',
                                     check=lambda m:
                                     m.author.id == 292212176494657536
                                     and m.embeds and str(ctx.author.id) in
                                     m.embeds[0].author.icon_url and m.channel.id == ctx.channel.id,
                                     timeout=15.0)
        e = msg.embeds[0]
        if e.title != 'Triggers':
            return await ctx.send('Failed to find a response with your highlights')
        imported_highlights = e.description.splitlines()
        added = 0
        for new_hl in imported_highlights:
            active = await ctx.bot.conn.fetch('SELECT kw FROM highlights WHERE user_id=$1', ctx.author.id)
            if len(active) >= MAX_HIGHLIGHTS:
                break
            if new_hl in [rec['kw'] for rec in active]:
                raise commands.CommandError('You already have a highlight with this trigger')
            await ctx.bot.conn.execute(
                'INSERT INTO highlights(user_id, kw, is_regex) VALUES ( $1, $2, $3 )',
                ctx.author.id, fr"{new_hl}", False)
            added += 1
        ctx.bot.dispatch('hl_update')
        await ctx.send(f'Imported {added} highlights')


def setup(bot):
    for command in HighlightCommands(bot).get_commands():
        bot.get_command('highlight').remove_command(command.name)
        bot.get_command('highlight').add_command(command)
    bot.add_cog(HlMon(bot))
