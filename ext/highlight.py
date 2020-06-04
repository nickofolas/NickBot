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

import discord
from discord.ext import commands, flags, tasks

from utils.checks import check_member_in_guild
from utils.config import conf

# Constants
MAX_HIGHLIGHTS = 10
PendingHighlight = namedtuple('PendingHighlight', ['user', 'embed'])

regex_check = re.compile(r"(?P<charmatching>(\.|\\w|\\S|\\D)[\*\+]|\[(a-z)?(A-­Z)?(0-9)?(_)?])|(?P<or>(\|.*){5})")


class Highlight:
    def __init__(self, user_id, kw, exclude_guild: list = None):
        self.user_id = user_id
        self.kw = kw
        self.exc_guilds = exclude_guild
        self.compiled = re.compile(kw, re.I)

    def __repr__(self):
        attrs = ' '.join(f"{k}={v}" for k, v in self.__dict__.items())
        return f"<{self.__class__.__name__} {attrs}>"

    def check_can_send(self, message, bot):
        predicates = []
        if not message.guild:
            return False
        if self.user_id not in [m.id for m in message.guild.members]:
            return False
        if self.exc_guilds:
            predicates.append(message.guild.id not in self.exc_guilds)
        predicates.append(not re.search(re.compile(r'([a-zA-Z0-9]{24}\.[a-zA-Z0-9]{6}\.[a-zA-Z0-9_\-]{27}|mfa\.['
                                                   r'a-zA-Z0-9_\-]{84})'), message.content))
        if blocks := bot.user_cache[self.user_id]['hl_blocks']:
            predicates.append(message.author.id not in blocks)
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
            hl_underline = m.content.replace(match.group(0), f'**__{match.group(0)}__**')
            repl = r'<a?:\w*:\d*>'
            context_list.append(
                f"{conf['default_discord_users'][avatar_index]} **{m.author.name}:** "
                f"{re.sub(repl, ':question:', hl_underline)}")
        context_list = reversed(context_list)
        embed = discord.Embed(
            title=f'A word has been highlighted!',
            description='\n'.join(context_list) + f'\n[Jump URL]({message.jump_url})',
            color=discord.Color.main)
        embed.timestamp = message.created_at
        return embed


class HlMon(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.cache = []
        self.queue = []
        bot.loop.create_task(self.update_highlight_cache())
        self.do_highlights.start()

    def cog_unload(self):
        self.do_highlights.cancel()

    @commands.Cog.listener(name='on_message')
    async def watch_highlights(self, msg):
        for hl in self.cache:
            if match := hl.compiled.search(msg.content):
                if hl.check_can_send(msg, self.bot) is False:
                    continue
                if len(self.queue) < 40 and self.queue.count(hl.user_id) < 5:
                    self.queue.append(PendingHighlight(self.bot.get_user(hl.user_id), (await hl.to_embed(match, msg))))

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
        finally:
            self.queue = []

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
    if len(kw) < 3:
        raise commands.CommandError(
            'Highlights must be more than 2 characters long')
    if s := regex_check.search(kw):
        d = s.groupdict()
        raise commands.CommandError(f"Disallowed regex character(s) {set(i for i in d.values() if i)}")


# noinspection PyMethodParameters
class HighlightCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @flags.add_flag('highlight', nargs='+')
    @flags.add_flag('-re', '--regex', action='store_true')
    @commands.command(cls=flags.FlagCommand)
    async def add(ctx, **flags):
        """
        Add a new highlight! When a highlighted word is used, you'll get notified!
        If the --regex flag is passed, the highlight will be compiled as a regex
        """
        subbed = re.sub(fr"{ctx.prefix}h(igh)?l(ight)? add", '', ctx.message.content)
        highlight_words = re.sub(r"--?re(gex)?", '', subbed).strip()
        if flags['regex']:
            check_regex(highlight_words)
        else:
            highlight_words = re.escape(highlight_words)
        active = await ctx.bot.conn.fetch('SELECT kw FROM highlights WHERE user_id=$1', ctx.author.id)
        if len(active) >= MAX_HIGHLIGHTS:
            raise commands.CommandError(f'You may only have {MAX_HIGHLIGHTS} highlights at a time')
        if highlight_words in [rec['kw'] for rec in active]:
            raise commands.CommandError('You already have a highlight with this trigger')
        await ctx.bot.conn.execute(
            'INSERT INTO highlights(user_id, kw) VALUES ( $1, $2 )',
            ctx.author.id, fr"{highlight_words}")
        ctx.bot.dispatch('hl_update')
        await ctx.message.add_reaction(ctx.tick(True))

    @commands.command(name='exclude', aliases=['mute', 'ignore', 'exc'])
    async def exclude_guild(ctx, highlight_index, guild_id: int = None):
        """Add and remove guilds to be ignored from highlight notifications.
        Currently ignored guilds will be un-ignored if passed a second time
        """
        if not index_check(highlight_index):
            raise commands.CommandError('Specify a highlight by its index (found in your list of highlights)')
        highlight_index = int(highlight_index)
        guild_id = guild_id or ctx.guild.id
        user_hl = [hl for hl in ctx.bot.get_cog("HlMon").cache if hl.user_id == ctx.author.id]
        current = user_hl[highlight_index - 1].exc_guilds
        strategy = "array_remove" if current and guild_id in current else "array_append"
        await ctx.bot.conn.execute(f'UPDATE highlights SET exclude_guild = {strategy}(exclude_guild, $1) WHERE '
                                   'user_id=$2 AND kw=$3',
                                   guild_id, ctx.author.id, user_hl[highlight_index - 1].kw)
        ctx.bot.dispatch('hl_update')
        await ctx.message.add_reaction(ctx.tick(True))

    @flags.add_flag('-a', '--add', nargs='*')
    @flags.add_flag('-r', '--remove', nargs='*')
    @commands.command(name='block', aliases=['blocks'], cls=flags.FlagCommand)
    async def hl_block(ctx, **flags):
        """Add or remove a user from your list of people who won't highlight you, or just view the list
        Use the --add flag to add a user, and use --remove to do the opposite"""
        if not flags.get('add') and not flags.get('remove'):
            if b := ctx.bot.user_cache[ctx.author.id]['hl_blocks']:
                blocked = [ctx.bot.get_user(i).__str__() for i in b]
            else:
                blocked = ["No blocked users"]
            await ctx.quick_menu(blocked, 10, delete_message_after=True)
            return
        strategy = 'array_append' if flags.get('add') else 'array_remove'
        person = await commands.UserConverter().convert(ctx, (flags.get('add') or flags.get('remove'))[0])
        async with ctx.loading():
            await ctx.bot.conn.execute(f"UPDATE user_data SET hl_blocks = {strategy}(hl_blocks, $1) WHERE "
                                       "user_id=$2", person.id, ctx.author.id)
            await ctx.bot.build_user_cache()

    @commands.command(name='info')
    async def view_highlight_info(ctx, highlight_index):
        """Display info on what triggers a specific highlight, or what guilds are muted from it"""
        if not index_check(highlight_index):
            raise commands.CommandError('Specify a highlight by its index (found in your list of highlights)')
        hl_index = int(highlight_index)
        hl_data = [hl for hl in ctx.bot.get_cog("HlMon").cache if hl.user_id == ctx.author.id][hl_index - 1]
        ex_guild_display = f"**Ignored Guilds** {', '.join([ctx.bot.get_guild(i).name for i in hl_data.exc_guilds])}" if \
            hl_data.exc_guilds else ''
        embed = discord.Embed(
            description=f'**Triggered by** "{hl_data.kw}"\n{ex_guild_display}',
            color=discord.Color.main)
        await ctx.send(embed=embed)

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
            try:
                check_regex(new_hl)
            except commands.CommandError:
                continue
            active = await ctx.bot.conn.fetch('SELECT kw FROM highlights WHERE user_id=$1', ctx.author.id)
            if len(active) >= MAX_HIGHLIGHTS:
                break
            if new_hl in [rec['kw'] for rec in active]:
                raise commands.CommandError('You already have a highlight with this trigger')
            await ctx.bot.conn.execute(
                'INSERT INTO highlights(user_id, kw) VALUES ( $1, $2 )',
                ctx.author.id, fr"{new_hl}")
            added += 1
        ctx.bot.dispatch('hl_update')
        await ctx.send(f'Imported {added} highlights')


def setup(bot):
    for command in HighlightCommands(bot).get_commands():
        bot.get_command('highlight').remove_command(command.name)
        bot.get_command('highlight').add_command(command)
    bot.add_cog(HlMon(bot))
