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
from textwrap import shorten

import discord
from discord.ext import commands, flags, tasks

import neo
from neo.types import TimedSet

# Constants
MAX_HIGHLIGHTS = 10
PendingHighlight = namedtuple('PendingHighlight', ['user', 'embed'])

regex_flag = re.compile(r"--?re(gex)?")
excessive_or = re.compile(r"(?<!\\)\|")
excessive_escapes = re.compile(r"(?<!\\)\\s|\\d|\\w", re.I)
regex_check = re.compile(r"""(?P<uncontrolled>[\*\+])|
                             (?<!\\)\{\d*(\,\s?\d*)?\}|
                             (?<!\\)\.""", re.I | re.X)
emoji_re = re.compile(r"<a?:[a-zA-Z0-9_]*:(?P<id>\d*)>", re.I)


def check_regex(content):
    if (match := regex_check.search(content)):
        d = regex_check.search(content).groupdict()
        if d.get('uncontrolled'):
            raise ValueError(f'Uncontrolled repetition match found [`{match.group(0)}`]')
        else:
            raise ValueError(f'Found disallowed pattern in `{match.group(0)}`')
    if (f := [*filter(lambda pat: len(pat.findall(content)) > 5, (excessive_or, excessive_escapes))]):
        raise ValueError(f'Excessive escapes/`|` chars [{[*map(lambda p: p.findall(content), f)]})')
    
def clean_emojis(content, bot):
    new_content = content
    for match in emoji_re.finditer(content):
        if not bot.get_emoji(int(match.groupdict()['id'])):
            new_content = content.replace(match.group(0), ':question:')
    return new_content

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
    async def to_embed(match, message, bot):
        context_list = []
        async for m in message.channel.history(limit=5):
            avatar_index = m.author.default_avatar.value
            hl_underline = m.content.replace(match, f'**__{match}__**') if m.id == message.id else m.content
            repl = r'<a?:\w*:\d*>'
            content = f"{neo.conf['emojis']['default_avs'][avatar_index]} **{m.author.name}:** " \
                      f"{clean_emojis(hl_underline, bot)}"
            if m.embeds:
                content += ' <:neoembed:728240626239406141>'
            if m.attachments:
                content += ' 🖼️'
            context_list.append(content)
        context_list.reverse()
        while len('\n'.join(context_list)) > 2048:
            context_list = context_list[1:]
        embed = neo.Embed(
            title=f'Highlighted in {message.guild.name}/#{message.channel.name} with "{shorten(match, width=25)}"',
            description='\n'.join(context_list) + f'\n[Jump URL]({message.jump_url})')
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
                self.queue.append(PendingHighlight(
                    self.bot.get_user(hl.user_id),
                    (await hl.to_embed(match, msg, self.bot))))

    @commands.Cog.listener(name='on_message')
    async def update_recents(self, msg):
        if msg.author.id in {hl.user_id for hl in self.cache}:
            if not self.recents.get(msg.channel.id):
                self.recents.update({msg.channel.id: TimedSet(decay_time=60, loop=self.bot.loop)})
            self.recents[msg.channel.id].add(msg.author.id)

    @commands.Cog.listener(name='on_hl_update')
    async def update_highlight_cache(self):
        await self.bot.wait_until_ready()
        self.cache = [Highlight(**dict(record)) for record in await self.bot.pool.fetch("SELECT * FROM highlights")]

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


def guild_or_user(bot, snowflake_id):
    return f'**User** {bot.get_user(snowflake_id)}' if bot.get_user(snowflake_id) else f'**Guild** {bot.get_guild(snowflake_id)}'

strategies = {'block': 'array_append', 'unblock': 'array_remove'}


class HighlightCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(usage="<highlight> [--regex]")
    async def add(ctx):
        """
        Add a new highlight! When a highlighted word is used, you'll get notified!
        If the --regex flag is passed, the highlight will be compiled as a regex
        __Regex highlights__ have some character restrictions to prevent abuse:
        - No more than 5 unescaped `|` or `\s`, `\d`, or `\w` (case insensitive)
        - Unescaped use of the `.` catch-all character is disallowed
        - Unescaped use of `{n}`, `{n,m}`, `*`, or `+` to match multiple characters is disallowed
        """
        cleaned_invocation = re.sub(fr"{re.escape(ctx.prefix)}h(igh)?l(ight)? add", '', ctx.message.content)
        highlight_words = regex_flag.sub('', cleaned_invocation).strip()
        with_regex = bool(regex_flag.search(ctx.message.content))
        if with_regex:
            check_regex(highlight_words)
        if len(highlight_words) < 2:
            raise commands.CommandError('Highlights must be more than 1 character long')
        active = await ctx.bot.pool.fetch('SELECT kw FROM highlights WHERE user_id=$1', ctx.author.id)
        if len(active) >= MAX_HIGHLIGHTS:
            raise commands.CommandError(f'You may only have {MAX_HIGHLIGHTS} highlights at a time')
        if highlight_words in [rec['kw'] for rec in active]:
            raise commands.CommandError('You already have a highlight with this trigger')
        await ctx.bot.pool.execute(
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
            await ctx.paginate(blocked, 10, delete_message_after=True)
            return
        strategy = strategies.get(ctx.invoked_with)
        snowflake = user_or_guild
        try:
            blocked = (await commands.UserConverter().convert(ctx, snowflake)).id
        except:
            blocked = int(snowflake)
        async with ctx.loading():
            await ctx.bot.pool.execute(
                f"UPDATE user_data SET hl_blocks = {strategy}(hl_blocks, $1) WHERE "
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
            await ctx.paginate(whitelisted, 10, delete_message_after=True)
            return
        strategy = 'array_append' if flags.get('add') else 'array_remove'
        snowflake = (flags.get('add') or flags.get('remove'))[0]
        async with ctx.loading():
            await ctx.bot.pool.execute(
                f"UPDATE user_data SET hl_whitelist = {strategy}(hl_whitelist, $1) WHERE "
                "user_id=$2", int(snowflake), ctx.author.id)
            await ctx.bot.user_cache.refresh()

    @commands.command(name='remove', aliases=['rm', 'delete', 'del', 'yeet'])
    async def remove_highlight(ctx, highlight_index: commands.Greedy[int]):
        """
        Remove one, or multiple highlights by index
        """
        if not highlight_index:
            raise commands.CommandError('Use the index of a highlight [found in your list of highlights] to remove it')
        query = """
        WITH enumerated AS (
        SELECT highlights.kw,row_number() OVER () AS rnum FROM highlights WHERE user_id=$1
        )
        DELETE FROM highlights WHERE user_id=$1 AND kw IN (
        SELECT enumerated.kw FROM enumerated WHERE enumerated.rnum=ANY($2::bigint[])
        ) RETURNING kw
        """
        deleted = await ctx.bot.pool.fetch(query, ctx.author.id, highlight_index)
        shown = [f" - `{shorten(record['kw'], width=175)}`" for record in deleted]
        extra = f'\n *+ {len(shown[5:])} more*' if len(shown[5:]) else ''
        await ctx.send('Successfully deleted the following highlights:\n{}'.format(
            '\n'.join(shown[:5]) + extra))
        ctx.bot.dispatch('hl_update')

    @commands.command(name='clear', aliases=['yeetall'])
    async def clear_highlights(ctx):
        """
        Completely wipe your list of highlights
        """
        confirm = await ctx.prompt('Are you sure you want to clear all highlights?')
        if confirm:
            await ctx.bot.pool.execute('DELETE FROM highlights WHERE user_id=$1', ctx.author.id)
            ctx.bot.dispatch('hl_update')

def setup(bot):
    for command in HighlightCommands(bot).get_commands():
        bot.get_command('highlight').remove_command(command.name)
        bot.get_command('highlight').add_command(command)
    bot.add_cog(HlMon(bot))
