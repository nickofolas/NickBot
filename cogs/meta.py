import inspect
import asyncio
import itertools
import os
from datetime import datetime
import sys

import discord
from discord.ext import commands
from utils.paginator import ShellMenu, Pages, CSMenu
import import_expression
import psutil
import humanize

from utils.config import conf
import utils


def retrieve_checks(command):
    req = []
    try:  # Tries to get the checks for a command
        for line in (source := inspect.getsource(command.callback)).splitlines():
            # Checks every line for elements
            # of the perm_list
            for permi in conf[
                    'perm_list']:
                # Confirms the perm is in a decorator
                # and appends it to required perms
                if permi in line and '@' in line:
                    req.append(
                        permi
                    )
    except Exception:
        pass
    return ', '.join(req)


# Using code provided by Rapptz under the MIT License
# Copyright ©︎ 2015 Rapptz
# R. Danny licensing:
# https://github.com/Rapptz/RoboDanny
"""
The MIT License (MIT)
Copyright (c) 2015 Rapptz
Permission is hereby granted, free of charge, to any person obtaining a
copy of this software and associated documentation files (the "Software"),
to deal in the Software without restriction, including without limitation
the rights to use, copy, modify, merge, publish, distribute, sublicense,
and/or sell copies of the Software, and to permit persons to whom the
Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.
"""


class HelpPaginator(Pages):
    def __init__(self, help_command, ctx, entries, *, per_page=4):
        super().__init__(ctx, entries=entries, per_page=per_page)
        self.reaction_emojis.append(
            ('\N{WHITE QUESTION MARK ORNAMENT}', self.show_bot_help))
        self.total = len(entries)
        self.help_command = help_command
        self.prefix = help_command.clean_prefix
        self.is_bot = False

    def get_bot_page(self, page):
        cog, description, commands = self.entries[page - 1]
        self.title = f'{cog} Commands'
        self.description = description
        return commands

    def prepare_embed(self, entries, page, *, first=False):
        self.embed.clear_fields()
        self.embed.description = self.description
        self.embed.title = self.title


        for entry in entries:
            signature = f'{entry.qualified_name} {entry.signature}'
            self.embed.add_field(
                name=signature,
                value=entry.short_doc or "No description found",
                inline=False)

        if self.maximum_pages:
            self.embed.set_author(name=f'Page {page}/{self.maximum_pages} ({self.total} commands)')

    async def show_bot_help(self):
        """Shows how to use the bot"""

        self.embed.title = 'Using the bot'
        self.embed.description = 'Hello! Welcome to the help page.'
        self.embed.clear_fields()

        entries = (
            ('<argument>', 'This means the argument is __**required**__.'),
            ('[argument]', 'This means the argument is __**optional**__.'),
            ('A|B', 'This means the it can be __**either A or B**__.'),
            ('[argument...]', 'This means you can have multiple arguments.\n' \
                              'Now that you know the basics, it should be noted that...\n' \
                              '__**You do not type in the brackets!**__')
        )

        self.embed.add_field(name='How do I use this bot?', value='Reading the bot signature is pretty simple.')

        for name, value in entries:
            self.embed.add_field(name=name, value=value, inline=False)

        self.embed.set_footer(text=f'We were on page {self.current_page} before this message.')
        await self.message.edit(embed=self.embed)

        async def go_back_to_current_page():
            await asyncio.sleep(30.0)
            await self.show_current_page()

        self.bot.loop.create_task(go_back_to_current_page())


class PaginatedHelpCommand(commands.HelpCommand):
    def __init__(self):
        super().__init__(command_attrs={
            'help': 'Shows help about the bot, a command, or a category'
        })

    async def on_help_command_error(self, ctx, error):
        if isinstance(error, commands.CommandInvokeError):
            await ctx.send(str(error.original))

    def get_command_signature(self, command):
        parent = command.full_parent_name
        if len(command.aliases) > 0:
            aliases = '|'.join(command.aliases)
            fmt = f'{command.name}|{aliases}'
            if parent:
                fmt = f'{parent} {fmt}'
            alias = fmt
        else:
            alias = command.name if not parent else f'{parent} {command.name}'
        return f'{alias} {command.signature}'

    async def send_bot_help(self, mapping):
        def key(c):
            return c.cog_name or '\u200bUncategorized'

        bot = self.context.bot
        entries = await self.filter_commands(bot.commands, sort=True, key=key)
        nested_pages = []
        per_page = 9
        total = 0

        for cog, commands in itertools.groupby(entries, key=key):
            commands = sorted(commands, key=lambda c: c.name)
            if len(commands) == 0:
                continue

            total += len(commands)
            actual_cog = bot.get_cog(cog)
            # get the description if it exists (and the cog is valid) or return Empty embed.
            description = (actual_cog and actual_cog.description) or discord.Embed.Empty
            nested_pages.extend((cog, description, commands[i:i + per_page]) for i in range(0, len(commands), per_page))

        # a value of 1 forces the pagination session
        pages = HelpPaginator(self, self.context, nested_pages, per_page=1)

        # swap the get_page implementation to work with our nested pages.
        pages.get_page = pages.get_bot_page
        pages.is_bot = True
        pages.total = total
        await pages.paginate()

    async def send_cog_help(self, cog):
        entries = await self.filter_commands(cog.get_commands(), sort=True)
        pages = HelpPaginator(self, self.context, entries)
        pages.title = f'{cog.qualified_name} Commands'
        pages.description = cog.description

        await pages.paginate()

    def common_command_formatting(self, page_or_embed, command):
        page_or_embed.title = self.get_command_signature(command)
        if command.description:
            page_or_embed.description = f'{command.description}\n\n{command.help}'
        else:
            page_or_embed.description = command.help or 'No description found'

    async def send_command_help(self, command):
        # No pagination necessary for a single command.
        embed = discord.Embed(colour=0x84cdff)
        self.common_command_formatting(embed, command)
        if retrieve_checks(command):
            embed.set_footer(text=f'Checks: {retrieve_checks(command)}')
        await self.context.send(embed=embed)

    async def send_group_help(self, group):
        subcommands = group.commands
        if len(subcommands) == 0:
            return await self.send_command_help(group)

        entries = await self.filter_commands(subcommands, sort=True)
        pages = HelpPaginator(self, self.context, entries)
        self.common_command_formatting(pages, group)
        if retrieve_checks(group):
            pages.embed.set_footer(text=f'Checks: {retrieve_checks(group)}')

        await pages.paginate()


class Meta(commands.Cog):
    """Commands relating to the bot itself"""

    def __init__(self, bot):
        self.bot = bot
        self.old_help = self.bot.help_command
        self.bot.help_command = PaginatedHelpCommand()
        self.bot.help_command.cog = self
        self.bot.loop.create_task(self.fetch_latest_commit())

    def cog_unload(self):
        self.bot.help_command = self.old_help

    @commands.group(invoke_without_command=True, aliases=['src'])
    @commands.is_owner()
    async def source(self, ctx, *, cmd):
        """Inspect and get the source code for any function or command"""
        try:
            cb = self.bot.get_command(cmd).callback
            lines = [
                line for line in inspect.getsource(cb)
                .replace('```', '`\N{zero width space}`')
            ]
        except Exception:
            func = import_expression.eval(cmd)
            lines = [
                line for line in inspect.getsource(func)
                .replace('```', '`\N{zero width space}`')
            ]
        entries = lines
        source = ShellMenu(entries, code_lang='py', per_page=1500)
        menu = CSMenu(source, delete_message_after=True)
        await menu.start(ctx)

    @source.command(name='github', aliases=['gh'])
    @commands.is_owner()
    async def github_link(self, ctx, *, cmd):
        c = self.bot.get_command(cmd).callback
        file = c.__code__.co_filename
        location = os.path.relpath(file)
        lines, first_line = inspect.getsourcelines(c)
        last_line = first_line + (len(lines) - 1)
        await ctx.send(f'<https://github.com/nickofolas/NickBot/blob/master/{location}#L{first_line}-L{last_line}>')

    @commands.command()
    @commands.cooldown(1, 240, commands.BucketType.user)
    async def suggest(self, ctx, *, suggestion):
        """Make a suggestion to the bot's dev"""
        owner = (await self.bot.application_info()).owner
        embed = discord.Embed(title='', description=f'> {suggestion}', color=discord.Color.main)
        embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.avatar_url_as(static_format='png'))
        embed.timestamp = ctx.message.created_at
        embed.set_footer(text=ctx.guild)
        await owner.send(embed=embed)
        await ctx.message.add_reaction(ctx.tick(True))

    @commands.command()
    async def cogs(self, ctx):
        """List all active cogs"""
        cog_listing = []
        for each_cog in sorted(self.bot.all_cogs):
            if each_cog in self.bot.cogs:
                cog_listing.append(
                    '<:c_:703740667926675536> ' + each_cog)
            elif each_cog not in self.bot.cogs:
                cog_listing.append(
                    '<:x_:703739402094117004> ' + each_cog
                )  # This bit gets the different cogs and
                # marks them as active or disabled
        embed = discord.Embed(
            title="All Cogs",
            description='\n' + '\n'.join(cog_listing),
            color=discord.Color.main)
        await ctx.send(embed=embed)

    async def fetch_latest_commit(self):
        headers = {'Authorization': f'token  {os.getenv("GITHUB_TOKEN")}'}
        url = 'https://api.github.com/repos/nickofolas/NickBot/commits'
        async with self.bot.session.get(f'{url}/master', headers=headers) as resp1, self.bot.session.get(url, headers=headers) as resp2:
            self.last_commit_cache = await resp1.json()
            self.all_commits = len(await resp2.json())

    @commands.group(invoke_without_command=True, aliases=['ab'])
    async def about(self, ctx):
        """Displays info about the bot"""
        appinfo = await self.bot.application_info()
        mem = psutil.virtual_memory()[2]
        vi = sys.version_info
        ascii_bar = utils.data_vis.bar_make(round(mem / 10), 10, '▰', '▱')
        delta_uptime = datetime.utcnow() - self.bot.launch_time
        embed = discord.Embed(color=discord.Color.main)
        embed.set_footer(text=f'Python {vi.major}.{vi.minor}.{vi.micro} | discord.py {discord.__version__}')
        embed.set_author(name=appinfo.owner)
        embed.add_field(
            name='**Bot Info**',
            value=f"""
**Current Uptime **{humanize.naturaldelta(delta_uptime)}
**Total Guilds **{len(self.bot.guilds):,}
**Available Emojis **{len(self.bot.emojis):,}
**Visible Users **{len(self.bot.users):,}
            """
            )
        embed.add_field(
            name='_ _',
            value=f"""
**Total Commands **{len(set(self.bot.walk_commands()))}
**Total Cogs **{len(self.bot.cogs)}
**Memory Usage **{mem}%
{ascii_bar}
            """
            )
        embed.add_field(
            name=f'**Latest Commit** - `{self.last_commit_cache["sha"][:7]}` - {self.all_commits} total',
            value=f'```\n{self.last_commit_cache["commit"]["message"]}\n```',
            inline=False
        )
        if ctx.author not in self.bot.get_guild(696739356815392779).members:
            embed.add_field(
                name='**Support**',
                value=f'Join the [support server](https://discord.gg/tjq68yq)',
                inline=False)
        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Meta(bot))
