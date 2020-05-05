from typing import Union
import time
from datetime import datetime, timedelta
import asyncio
import random
import copy
import re
import string

import asyncpg
import discord
from discord.ext import commands
import aiosqlite as asq
import humanize

from utils.paginator import BareBonesMenu, CSMenu
from utils.helpers import pluralize


class Data(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # BEGIN HIGHLIGHTS GROUP ~

    @commands.group(aliases=['hl'], invoke_without_command=True)
    async def highlight(self, ctx):
        """
        Base command for keyword highlights. Run with no arguments to list your active highlights.
        """
        hl_list = []
        fetched = [rec['kw'] for rec in await self.bot.conn.fetch('SELECT kw FROM highlights WHERE user_id=$1', ctx.author.id)]
        for i in range(10):
            to_append = f"`{(i + 1)}` {fetched[i]}" if i < len(fetched) else ''
            hl_list.append(to_append)
        await ctx.send(embed=discord.Embed(
            description='\n'.join(hl_list), color=discord.Color.main).set_footer(
            text=f'{len(fetched)}/10 slots used'))

    @highlight.command()
    async def add(self, ctx, *, highlight_words):
        """
        Add a new highlight! When a highlighted word is used, you'll get notified!
        If desired, the highlight can be made quite granular, as regex patterns are
        supported.
        NOTE: It may take up to a minute for a new highlight to take effect
        """
        if len(highlight_words) < 3 or len(highlight_words) > 60:
            raise commands.CommandError('Highlights must be more than 2 characters long and at most 60 characters long')
        content_check = re.compile(fr'{highlight_words}', re.I)
        for i in ('afssafasfa', '12421', '\n', ' ', string.ascii_letters, string.digits):
            if re.search(content_check, i):
                raise commands.CommandError('This trigger is too general')
        active = await self.bot.conn.fetch('SELECT kw FROM highlights WHERE user_id=$1', ctx.author.id)
        if len(active) >= 10:
            raise commands.CommandError('You may only have 10 highlights at a time')
        if highlight_words in [rec['kw'] for rec in active]:
            raise commands.CommandError('You already have a highlight with this trigger')
        await self.bot.conn.execute(
            'INSERT INTO highlights(user_id, kw) VALUES ( $1, $2 )',
            ctx.author.id, fr"{highlight_words}")
        await ctx.message.add_reaction(ctx.tick(True))

    @highlight.command(name='exclude', aliases=['mute', 'ignore', 'exc'])
    async def exclude_guild(self, ctx, highlight_index: int, guild_id: str = None):
        """Add and remove guilds to be ignored from highlight notifications.
        Specify which highlight to ignore via its index
            - To ignore from the current guild, pass no further arguments
            - To ignore from another guild, pass that guild's id
        If the specified guild is not being ignored, then it will be added to the list
        of ignored guilds
            - If the specified guild is already being ignored, running the command,
            and passing that guild a second time will remove it from the list
        NOTE: It may take up to a minute for this to take effect"""
        guild_id = guild_id or str(ctx.guild.id)
        iterable_hls = [(rec['kw'], rec['exclude_guild'])
                        for rec in
                        await self.bot.conn.fetch(
                            'SELECT kw, exclude_guild FROM highlights WHERE user_id=$1', ctx.author.id)]
        current = iterable_hls[highlight_index - 1][1]
        if current is not None:
            current = current.split(',')
            if guild_id in current:
                del (current[current.index(guild_id)])
            else:
                current.append(guild_id)
            current = ','.join(current)
        else:
            current = guild_id
        await self.bot.conn.execute(
            'UPDATE highlights SET exclude_guild=$1 WHERE user_id=$2 AND kw=$3',
            current, ctx.author.id, iterable_hls[highlight_index - 1][0])
        await ctx.message.add_reaction(ctx.tick(True))

    @highlight.command(name='info')
    async def view_highlight_info(self, ctx, highlight_index: int):
        """Display info on what triggers a specific highlight, or what guilds are muted from it"""
        hl_data = tuple(
            (await self.bot.conn.fetch('SELECT * FROM highlights WHERE user_id=$1',ctx.author.id))[highlight_index-1])
        excluded_list = None
        if hl_data[2] not in (None, ''):
            excluded_list = hl_data[2].split(',')
            excluded_guilds = [self.bot.get_guild(int(g)).name for g in excluded_list if g not in ('', None)]
        ex_guild_display = f"**Ignored Guilds** {', '.join(excluded_guilds)}" if excluded_list else ''
        embed = discord.Embed(
            description=f'**Triggered by** "{hl_data[1]}"\n{ex_guild_display}',
            color=discord.Color.main)
        await ctx.send(embed=embed)

    @highlight.command(name='remove', aliases=['rm', 'delete', 'del', 'yeet'])
    async def remove_highlight(self, ctx, highlight_index: commands.Greedy[int]):
        """
        Remove one, or multiple highlights by index
        NOTE: It may take up to a minute for this to take effect
        """
        for i in highlight_index:
            try:
                int(i)
            except Exception:
                raise TypeError
        fetched = [rec['kw'] for rec in
                   await self.bot.conn.fetch("SELECT kw from highlights WHERE user_id=$1", ctx.author.id)]
        for num in highlight_index:
            await self.bot.conn.execute('DELETE FROM highlights WHERE user_id=$1 AND kw=$2',
                                        ctx.author.id, fetched[num - 1])
        await ctx.message.add_reaction(ctx.tick(True))

    @highlight.command(name='test')
    async def test_highlight(self, ctx, *, message):
        """Test your highlights by simulating a message event
        Pass a message that contains a highlights, and the
        bot will simulate someone else sending that message, so you
        can see what your highlight looks like in action."""
        copied_message = copy.copy(ctx.message)
        copied_message.content = message
        filtered_members = [m for m in ctx.guild.members if m != ctx.author and not m.bot]
        copied_message.author = random.choice(filtered_members)
        self.bot.dispatch('message', copied_message)
        await ctx.message.add_reaction(ctx.tick(True))

    @highlight.command(name='clear', aliases=['yeetall'])
    async def clear_highlights(self, ctx):
        """
        Completely wipe your list of highlights
        NOTE: It may take up to a minute for this to take effect
        """
        conf = await ctx.prompt('Are you sure you want to clear all highlights?')
        if conf:
            await self.bot.conn.execute('DELETE FROM highlights WHERE user_id=$1', ctx.author.id)

    @highlight.group(name='dev')
    @commands.is_owner()
    async def hl_dev(self, ctx):
        pass

    @hl_dev.command(name='queue')
    @commands.is_owner()
    async def view_hl_queue(self, ctx):
        await ctx.safe_send(str(self.bot.get_cog('Events').hl_queue))

    @hl_dev.command(name='cache')
    @commands.is_owner()
    async def view_hl_cache(self, ctx):
        await ctx.safe_send(str(self.bot.get_cog('Events').hl_cache))

    @hl_dev.command(name='build')
    @commands.is_owner()
    async def hl_cache_build_cmd(self, ctx):
        await self.bot.get_cog('Events').build_hl_cache()
        await ctx.message.add_reaction(ctx.tick(True))

    # END HIGHLIGHTS GROUP ~
    # BEGIN TODOS GROUP ~

    @commands.group(name='todo', invoke_without_command=True)
    async def todo_rw(self, ctx):
        """
        Base todo command, run with now arguments to see a list of all your active todos
        """
        todo_list = []
        fetched = [rec['content'] for rec in
                   await self.bot.conn.fetch("SELECT content from todo WHERE user_id=$1", ctx.author.id)]
        for count, value in enumerate(fetched, 1):
            todo_list.append(f'`{count}` {value}')
        if not todo_list:
            todo_list.append('No todos')
        source = BareBonesMenu(todo_list, per_page=10)
        menu = CSMenu(source, delete_message_after=True)
        await menu.start(ctx)

    @todo_rw.command(name='add')
    async def create_todo(self, ctx, *, content: str):
        """
        Add an item to your todo list
        """
        await self.bot.conn.execute('INSERT INTO todo VALUES ($1, $2)', ctx.author.id, content)
        await ctx.message.add_reaction(ctx.tick(True))

    @todo_rw.command(name='remove', aliases=['rm', 'delete', 'del', 'yeet'])
    async def remove_todo(self, ctx, todo_index: commands.Greedy[int]):
        """
        Remove one, or multiple todos by index
        """
        fetched = [rec['content'] for rec in
                   await self.bot.conn.fetch("SELECT content from todo WHERE user_id=$1", ctx.author.id)]
        for num in todo_index:
            await self.bot.conn.execute('DELETE FROM todo WHERE user_id=$1 AND content=$2',
                                        ctx.author.id, fetched[num - 1])
        await ctx.message.add_reaction(ctx.tick(True))

    @todo_rw.command(name='clear')
    async def clear_todos(self, ctx):
        """
        Completely wipe your list of todos
        """
        conf = await ctx.prompt('Are you sure you want to clear all todos?')
        if conf:
            await self.bot.conn.execute('DELETE FROM todo WHERE user_id=$1', ctx.author.id)

    # END TODOS GROUP ~
    # BEGIN TAGS GROUP ~

    @commands.group(invoke_without_command=True)
    @commands.cooldown(1, 2.5, commands.BucketType.user)
    async def tag(self, ctx, *, tag_name: str):
        """View a tag with the specified name"""
        # async with ctx.ExHandler(propagate=(self.bot, ctx), message='Tag not found'):
        rec = await self.bot.conn.fetch('SELECT tagbody FROM tags WHERE tagname=$1', tag_name.lower())
        await ctx.safe_send(rec[0]['tagbody'])
        await self.bot.conn.execute(
            'UPDATE tags SET times_used=times_used+1, usage_epoch=$1 WHERE tagname=$2',
            datetime.utcnow(), tag_name)

    @tag.command(name='create')
    async def create_tag(self, ctx, name: str = None, *, body: str = None):
        """Create a tag with the specified name and content
        This can be used in 2 different ways:
            - The first option is to create a tag in one command. This is
            accomplished by entering the tag name, and content all in the
            command invocation. It is important to note that if you wish
            to include spaces in the tag name, the name must be surrounded
            in quotes
            - The second option is to pass no arguments, which will launch
            an interactive tag creation prompt. This will allow you to enter
            the tag's name and content independently of each other, so quotes
            are **not** required
        If desired, images can also be appended to the tag's content"""
        msg = ctx.message
        if name is None and body is None:
            async with ctx.ExHandler(
                    propagate=(self.bot, ctx),
                    exception_type=asyncio.TimeoutError,
                    message='Prompt timed out!'):
                await ctx.send('What would you like the tag to be named?')
                msg = await self.bot.wait_for(
                    'message',
                    check=lambda m: m.author.id == ctx.author.id,
                    timeout=60.0)
                name = msg.content
                await ctx.send(f'The tag is named **{name}**. What is its content?')
                msg = await self.bot.wait_for(
                    'message',
                    check=lambda m: m.author.id == ctx.author.id,
                    timeout=300.0)
                body = msg.content
        if name in ('create', 'delete', 'del', 'info', 'edit', 'list', 'lb'):
            raise commands.CommandError('This name cannot be used')
        if attach := msg.attachments:
            body = (body + ' ' + attach[0].url) if body else attach[0].url
        try:
            await self.bot.conn.execute(
                'INSERT INTO tags (owner_id, tagname, tagbody, usage_epoch) VALUES ($1, $2, $3, $4)',
                ctx.author.id, name.lower(), body, datetime.utcnow())
        except asyncpg.exceptions.UniqueViolationError:
            raise commands.CommandError('A tag with this name already exists')
        await ctx.send('Tag successfully created')

    @tag.command(name='delete', aliases=['del'])
    async def delete_tag(self, ctx, *, tag_name: str):
        """Delete an owned tag"""
        if ctx.author.id == self.bot.owner_id:
            await self.bot.conn.execute(
                'DELETE FROM tags WHERE tagname=$1',
                tag_name.lower()
            )
        else:
            await self.bot.conn.execute(
                'DELETE FROM tags WHERE owner_id=$1 AND tagname=$2',
                ctx.author.id, tag_name.lower())
        await ctx.message.add_reaction(ctx.tick(True))

    @tag.command(name='info')
    async def view_tag_info(self, ctx, *, tag_name):
        """View details on a tag, such as times used and tag owner"""
        rec = await self.bot.conn.fetch('SELECT * FROM tags WHERE tagname=$1', tag_name.lower())
        if r := rec[0]:
            owner_id, tagname, tagcontent, tagusage, tagepoch = \
                r['owner_id'], r['tagname'], r['tagbody'], r['times_used'], r['usage_epoch']
        else:
            return
        last_used = humanize.naturaltime(
            datetime.utcnow() - tagepoch
        ) if tagepoch else None
        embed = discord.Embed(color=discord.Color.main)
        embed.add_field(name='Tag Info', value=f"""
**Name** {tagname}
**Owner** {(await self.bot.fetch_user(owner_id))}
**Times used** {tagusage}
**Last used** {last_used}
        """)
        await ctx.send(embed=embed)

    @tag.command(name='edit')
    async def edit_tag(self, ctx, tag_name: str, *, new_content):
        """Change the content of a specified tag that you own"""
        await self.bot.conn.execute(
            'UPDATE tags SET tagbody=$1 WHERE tagname=$2 AND owner_id=$3',
            new_content, tag_name.lower(), ctx.author.id)
        await ctx.message.add_reaction(ctx.tick(True))

    @tag.command(name='list')
    async def list_owned_tags(self, ctx, target: Union[discord.Member, discord.User] = None):
        """View all of your, or another's owned tags"""
        target = target or ctx.author
        tag_list = []
        fetched = [rec['tagname'] for rec in await self.bot.conn.fetch('SELECT tagname from tags WHERE owner_id=$1',
                                                                       target.id)]
        for count, value in enumerate(fetched, 1):
            tag_list.append(f'`{count}` {value}')
        if not tag_list:
            tag_list.append('No tags')
        source = BareBonesMenu(tag_list, per_page=10)
        menu = CSMenu(source, delete_message_after=True)
        await menu.start(ctx)

    @tag.command(name='lb')
    async def tag_leaderboard(self, ctx):
        top_tags = [(rec['tagname'], rec['times_used']) for rec in
                    await self.bot.conn.fetch('SELECT tagname, times_used FROM tags ORDER BY times_used DESC LIMIT 3')]
        top_owner = [(rec['owner_id'], rec['sum']) for rec in
                     await self.bot.conn.fetch('SELECT owner_id, SUM(times_used) as S FROM tags GROUP BY owner_id'
                                               ' ORDER BY SUM(times_used) DESC LIMIT 3')]
        embed = discord.Embed(title='Tag Leaderboard', color=discord.Color.main)
        embed.add_field(
            name='Top Tags',
            value='\n'.join([f'`{t[0]}` - {t[1]} uses' for t in top_tags]))
        embed.add_field(
            name='Top Owners',
            value='\n'.join([f'`{t[0]}` - {t[1]} uses' for t in top_owner]))
        await ctx.send(embed=embed)


    @tag.command(name='purge')
    @commands.is_owner()
    async def purge_inactive_tags(self, ctx, days: int = 7):
        """Purge tags, defaults to tags that haven't been used for 7 days and less than 10 times"""
        seven_days_epoch = datetime.utcnow() - timedelta(days=days)
        to_purge = await self.bot.conn.fetch('SELECT * FROM tags WHERE usage_epoch<$1', seven_days_epoch)
        prompt = await ctx.prompt(
            f'Are you sure you want to purge {len(to_purge)} {pluralize("tag", to_purge)}?')
        if prompt:
            await self.bot.conn.execute('DELETE FROM tags WHERE usage_epoch<$1 AND times_used<10', seven_days_epoch)
            await self.bot.get_user(self.bot.owner_id).send(f'Deleted tags: {to_purge}')

    # END TAGS GROUP ~


def setup(bot):
    bot.add_cog(Data(bot))
