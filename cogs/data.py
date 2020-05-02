from typing import Union
import time
from datetime import datetime, timedelta
import asyncio
import random
import copy
import re
import string

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
        async with asq.connect('./database.db') as db:
            async with db.execute('SELECT kw FROM highlights WHERE user_id=$1', (ctx.author.id,)) as cur:
                iterable_hls = [item[0] async for item in cur]
                for i in range(10):
                    to_append = f"`{(i+1)}` {iterable_hls[i]}" if i<len(iterable_hls) else f"`{i+1}` Unused"
                    hl_list.append(to_append)
        await ctx.send(embed=discord.Embed(
            description='\n'.join(hl_list), color=discord.Color.main))

    @highlight.command()
    async def add(self, ctx, *, highlight_words):
        """
        Add a new highlight! When a highlighted word is used, you'll get notified!
        If desired, the highlight can be made quite granular, as regex patterns are
        supported.
        NOTE: It may take up to a minute for a new highlight to take effect
        """
        if len(highlight_words) < 2 or len(highlight_words) > 60:
            raise commands.CommandError('Highlights must be at least 2 characters long and at most 60 characters long')
        content_check = re.compile(fr'{highlight_words}', re.I)
        for i in ('afssafasfa', '12421', '\n', ' ', string.ascii_letters, string.digits):
            if re.search(content_check, i):
                raise commands.CommandError('This trigger is too general')
        async with asq.connect('./database.db') as db:
            check = await db.execute('SELECT kw FROM highlights WHERE user_id=$1', (ctx.author.id,))
            if len(active := await check.fetchall()) == 10:
                raise commands.CommandError('You may only have 10 highlights at a time')
            if highlight_words in [a[0] for a in active]:
                raise commands.CommandError('You already have a highlight with this trigger')
            await db.execute('INSERT INTO highlights(user_id, kw) VALUES ( $1, $2 )', (ctx.author.id, fr"{highlight_words}"))
            await db.commit()
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
        async with asq.connect('./database.db') as db:
            async with db.execute('SELECT kw, exclude_guild FROM highlights WHERE user_id=$1', (ctx.author.id,)) as cur:
                iterable_hls = [item async for item in cur]
            current = iterable_hls[highlight_index-1][1]
            if current is not None:
                current = current.split(',')
                if guild_id in current:
                    del(current[current.index(guild_id)])
                else:
                    current.append(guild_id)
                current = ','.join(current)
            else:
                current = guild_id
            await db.execute(
                'UPDATE highlights SET exclude_guild=$1 WHERE user_id=$2 AND kw=$3',
                (current, ctx.author.id, iterable_hls[highlight_index-1][0]))
            await db.commit()
            await ctx.message.add_reaction(ctx.tick(True))

    @highlight.command(name='info')
    async def view_highlight_info(self, ctx, highlight_index: int):
        """Display info on what triggers a specific highlight, or what guilds are muted from it"""
        async with asq.connect('./database.db') as db:
            async with db.execute('SELECT * FROM highlights WHERE user_id=$1', (ctx.author.id,)) as cur:
                hl_data = [item async for item in cur][highlight_index-1]
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
        async with asq.connect('./database.db') as db:
            async with db.execute('SELECT kw FROM highlights WHERE user_id=$1', (ctx.author.id,)) as cur:
                iterable_hls = [item[0] async for item in cur]
            for num in highlight_index:
                await db.execute('DELETE FROM highlights WHERE user_id=$1 AND kw=$2', (ctx.author.id, iterable_hls[num-1]))
                await db.commit()
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
            async with asq.connect('./database.db') as db:
                await db.execute('DELETE FROM highlights WHERE user_id=$1', (ctx.author.id,))
                await db.commit()
            return

    # END HIGHLIGHTS GROUP ~
    # BEGIN TODOS GROUP ~

    @commands.group(name='todo', invoke_without_command=True)
    async def todo_rw(self, ctx):
        """
        Base todo command, run with now arguments to see a list of all your active todos
        """
        todo_list = []
        async with asq.connect('./database.db') as db:
            async with db.execute('SELECT content FROM todo WHERE user_id=$1', (ctx.author.id,)) as cur:
                iterable_todos = [item[0] async for item in cur]
                for count, value in enumerate(iterable_todos, 1):
                    todo_list.append(f'`{count}` {value}')
                if todo_list == []:
                    todo_list.append('No todos')
        source = BareBonesMenu(todo_list, per_page=10)
        menu = CSMenu(source, delete_message_after=True)
        await menu.start(ctx)

    @todo_rw.command(name='add')
    async def create_todo(self, ctx, *, content: str):
        """
        Add an item to your todo list
        """
        async with asq.connect('./database.db') as db:
            await db.execute('INSERT INTO todo VALUES($1, $2)', (ctx.author.id, content))
            await db.commit()
        await ctx.message.add_reaction(ctx.tick(True))

    @todo_rw.command(name='remove', aliases=['rm', 'delete', 'del', 'yeet'])
    async def remove_todo(self, ctx, todo_index: commands.Greedy[int]):
        """
        Remove one, or multiple todos by index
        """
        async with asq.connect('./database.db') as db:
            async with db.execute('SELECT content FROM todo WHERE user_id=$1', (ctx.author.id,)) as cur:
                iterable_todos = [item[0] async for item in cur]
            for num in todo_index:
                await db.execute('DELETE FROM todo WHERE user_id=$1 AND content=$2', (ctx.author.id, iterable_todos[num-1]))
                await db.commit()
        await ctx.message.add_reaction(ctx.tick(True))

    @todo_rw.command(name='clear')
    async def clear_todos(self, ctx):
        """
        Completely wipe your list of todos
        """
        conf = await ctx.prompt('Are you sure you want to clear all todos?')
        if conf:
            async with asq.connect('./database.db') as db:
                await db.execute('DELETE FROM todo WHERE user_id=$1', (ctx.author.id,))
                await db.commit()
            return
        else:
            return

    # END TODOS GROUP ~
    # BEGIN TAGS GROUP ~

    @commands.group(invoke_without_command=True)
    @commands.cooldown(1, 2.5, commands.BucketType.user)
    async def tag(self, ctx, *, tag_name: str):
        """View a tag with the specified name"""
        async with ctx.ExHandler(propagate=(self.bot, ctx), message='Tag not found'):
            async with asq.connect('./database.db') as db:
                sel = await db.execute('SELECT tagbody FROM tags WHERE tagname=$1', (tag_name.lower(),))
                res = await sel.fetchone()
                await ctx.safe_send(res[0])
                await db.execute('UPDATE tags SET times_used=times_used+1, usage_epoch=$1 WHERE tagname=$2', (time.time(), tag_name))
                await db.commit()

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
        async with asq.connect('./database.db') as db:
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
            if name in ('create', 'delete', 'del', 'info', 'edit', 'list'):
                raise commands.CommandError('This name cannot be used')
            res = await db.execute('SELECT EXISTS(SELECT 1 FROM tags WHERE tagname=$1)', (name.lower(),))
            if attach := msg.attachments:
                body = (body + ' ' + attach[0].url) if body else attach[0].url
            if (await res.fetchone())[0] >= 1:
                raise commands.CommandError('A tag with this name already exists!')
            await db.execute('INSERT INTO tags (owner_id, tagname, tagbody, usage_epoch) VALUES ($1, $2, $3, $4)', (ctx.author.id, name.lower(), body, time.time()))
            await db.commit()
        await ctx.send('Tag successfully created')

    @tag.command(name='delete', aliases=['del'])
    async def delete_tag(self, ctx, *, tag_name: str):
        """Delete an owned tag"""
        async with asq.connect('./database.db') as db:
            res = await db.execute('DELETE FROM tags WHERE owner_id=$1 AND tagname=$2', (ctx.author.id, tag_name.lower()))
            if res.rowcount < 1:
                if ctx.author.id == self.bot.owner_id:
                    await db.execute('DELETE FROM tags WHERE tagname=$2', (tag_name.lower(),))
                else:
                    raise commands.CommandError("Couldn't find this tag in your list of tags!")
            await db.commit()
        await ctx.message.add_reaction(ctx.tick(True))

    @tag.command(name='info')
    async def view_tag_info(self, ctx, *, tag_name):
        """View details on a tag, such as times used and tag owner"""
        async with asq.connect('./database.db') as db:
            sel = await db.execute('SELECT * FROM tags WHERE tagname=$1', (tag_name.lower(),))
            res = await sel.fetchone()
            if res:
                owner_id, tagname, tagcontent, tagusage, tagepoch = res
        last_used = humanize.naturaltime(
            datetime.utcnow() - datetime.utcfromtimestamp(tagepoch)
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
        async with asq.connect('./database.db') as db:
            await db.execute('UPDATE tags SET tagbody=$1 WHERE tagname=$2 AND owner_id=$3', (new_content, tag_name.lower(), ctx.author.id))
            await db.commit()
        await ctx.message.add_reaction(ctx.tick(True))

    @tag.command(name='list')
    async def list_owned_tags(self, ctx, target: Union[discord.Member, discord.User] = None):
        """View all of your, or another's owned tags"""
        target = target or ctx.author
        tag_list = []
        async with asq.connect('./database.db') as db:
            async with db.execute('SELECT tagname FROM tags WHERE owner_id=$1', (target.id,)) as cur:
                iterable_tags = [item[0] async for item in cur]
                for count, value in enumerate(iterable_tags, 1):
                    tag_list.append(f'`{count}` {value}')
                if tag_list == []:
                    tag_list.append('No tags')
        source = BareBonesMenu(tag_list, per_page=10)
        menu = CSMenu(source, delete_message_after=True)
        await menu.start(ctx)

    @tag.command(name='purge')
    @commands.is_owner()
    async def purge_inactive_tags(self, ctx, days: int = 7):
        """Purge tags, defaults to tags that haven't been used for 7 days and less than 10 times"""
        seven_days_epoch = datetime.timestamp(datetime.utcnow() - timedelta(days=days))
        async with asq.connect('./database.db') as db:
            async with db.execute('SELECT * FROM tags WHERE usage_epoch<$1', (seven_days_epoch,)) as re:
                to_purge = await re.fetchall()
                prompt = await ctx.prompt(f'Are you sure you want to purge {len(to_purge)} {pluralize("tag", to_purge)}?')
                if prompt:
                    await db.execute('DELETE FROM tags WHERE usage_epoch<$1 AND times_used<10', (seven_days_epoch,))
                    await db.commit()
                    await self.bot.get_user(self.bot.owner_id).send(f'Deleted tags: {to_purge}')

    # END TAGS GROUP ~


def setup(bot):
    bot.add_cog(Data(bot))
