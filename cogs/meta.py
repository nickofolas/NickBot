import inspect
import itertools
import os
import sys
import textwrap
from datetime import datetime
from contextlib import suppress

import discord
import humanize
import import_expression
import psutil
from discord.ext import commands

import utils
from utils.config import conf
from utils.paginator import ShellMenu, Pages, CSMenu


checked_perms = ['is_owner', 'guild_only', 'dm_only', 'is_nsfw']
checked_perms.extend([p[0] for p in discord.Permissions()])


def retrieve_checks(command):
    req = []
    with suppress(Exception):
        for line in inspect.getsource(command.callback).splitlines():
            for permi in checked_perms:
                if permi in line and line.lstrip().startswith('@'):
                    req.append(permi)
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
    def __init__(self, help_command, ctx, entries, *, per_page=4, footer_extra:str=None):
        super().__init__(ctx, entries=entries, per_page=per_page)
        self.total = len(entries)
        self.help_command = help_command
        self.prefix = help_command.clean_prefix
        self.is_bot = False
        self.footer_extra = footer_extra

    def get_bot_page(self, page):
        cog, description, commands = self.entries[page - 1]
        self.title = f'Category: {cog}'
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
            if self.footer_extra:
                self.embed.set_footer(text=f'Page {page}/{self.maximum_pages}{self.footer_extra}')
            else:
                self.embed.set_footer(text=f'Page {page}/{self.maximum_pages}')


class PaginatedHelpCommand(commands.HelpCommand):
    def __init__(self):
        super().__init__(command_attrs={
            'help': 'Shows help.'
        })

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
        per_page = 7
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
        pages.title = f'Category: {cog.qualified_name}'
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
        embed = discord.Embed(colour=discord.Color.main)
        self.common_command_formatting(embed, command)
        if retrieve_checks(command):
            embed.set_footer(text=f'Checks: {retrieve_checks(command)}')
        await self.context.send(embed=embed)

    async def send_group_help(self, group):
        subcommands = group.commands
        if len(subcommands) == 0:
            return await self.send_command_help(group)

        entries = await self.filter_commands(subcommands, sort=True)
        checks = None
        if c := retrieve_checks(group):
            checks = f' | Checks: {c}' 
        pages = HelpPaginator(self, self.context, entries, footer_extra=checks)
        self.common_command_formatting(pages, group)
        if c:
            pages.embed.set_footer(text=f'Checks: {c}')
        await pages.paginate()


class EmbeddedMinimalHelpCommand(commands.MinimalHelpCommand):
    def __init__(self):
        super().__init__(command_attrs={
            'help': 'Shows help.',
            'cooldown': commands.Cooldown(1, 2.5, commands.BucketType.user)
        })

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
        return f'{self.clean_prefix}{alias} {command.signature}'

    async def send_bot_help(self, mapping):
        def key(c):
            return c.cog_name or '\u200bUncategorized'
        bot = self.context.bot
        embed = discord.Embed(color=discord.Color.main).set_author(
            name=f'{self.context.me.name} Help', icon_url=self.context.me.avatar_url_as(static_format='png'))
        description = f'Use `{self.clean_prefix}help <command/category>` for more help\n\n'
        entries = await self.filter_commands(bot.commands, sort=True, key=key)
        for cog, cmds in itertools.groupby(entries, key=key):
            cmds = sorted(cmds, key=lambda c: c.name)
            description += f'**__{cog}__**\n{" • ".join([c.name for c in cmds])}\n'
        embed.description = description
        await self.context.send(embed=embed)

    async def send_cog_help(self, cog):
        embed = discord.Embed(title=f'{cog.qualified_name} Category', color=discord.Color.main)
        description = f'{cog.description or ""}\n\n'
        entries = await self.filter_commands(cog.get_commands(), sort=True)
        description += "\n".join([f'⇾ {c.name} - {c.short_doc or "No description"}' for c in entries])
        embed.description = description
        await self.context.send(embed=embed)

    async def send_command_help(self, command):
        embed = discord.Embed(title=self.get_command_signature(command), color=discord.Color.main)
        description = f'{command.help or "No description provided"}\n\n'
        embed.description = description
        if c := retrieve_checks(command):
            embed.set_footer(text=f'Checks: {c}')
        await self.context.send(embed=embed)

    async def send_group_help(self, group):
        embed = discord.Embed(title=self.get_command_signature(group), color=discord.Color.main)
        description = f'{group.help or "No description provided"}\n\n'
        entries = await self.filter_commands(group.commands, sort=True)
        description += "\n".join([f'⇾ {c.name} - {c.short_doc or "No description"}' for c in entries])
        embed.description = description
        if c := retrieve_checks(group):
            embed.set_footer(text=f'Checks: {c}')
        await self.context.send(embed=embed)


class Meta(commands.Cog):
    """Commands relating to the bot itself"""

    def __init__(self, bot):
        self.bot = bot
        self.old_help = self.bot.help_command
        self.bot.help_command = EmbeddedMinimalHelpCommand()
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
        except AttributeError:
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
    async def cogs(self, ctx):
        """List all active cogs"""
        cog_listing = []
        for each_cog in sorted(self.bot.all_cogs):
            if each_cog in self.bot.cogs:
                cog_listing.append(ctx.tick(True) + each_cog)
            elif each_cog not in self.bot.cogs:
                cog_listing.append(ctx.tick(False) + each_cog)  # This bit gets the different cogs and
                # marks them as active or disabled
        embed = discord.Embed(
            title="All Cogs",
            description='\n' + '\n'.join(cog_listing),
            color=discord.Color.main)
        await ctx.send(embed=embed)

    async def fetch_latest_commit(self):
        headers = {'Authorization': f'token  {os.getenv("GITHUB_TOKEN")}'}
        url = 'https://api.github.com/repos/nickofolas/NickBot/commits'
        async with self.bot.session.get(f'{url}/master', headers=headers) as resp1:
            self.last_commit_cache = await resp1.json()

    @commands.group(invoke_without_command=True, aliases=['ab', 'info'])
    async def about(self, ctx):
        """Displays info about the bot"""
        appinfo = await self.bot.application_info()
        mem = psutil.virtual_memory()[2]
        vi = sys.version_info
        ascii_bar = utils.data_vis.bar_make(round(mem / 10), 10, '▰', '▱')
        delta_uptime = datetime.utcnow() - self.bot.launch_time
        embed = discord.Embed(color=discord.Color.main)
        embed.set_footer(text=f'Python {vi.major}.{vi.minor}.{vi.micro} | discord.py {discord.__version__}')
        embed.set_author(name=f'Owner: {appinfo.owner}')
        embed.add_field(
            name='**Bot Info**',
            value=f"""
**Current Uptime **{humanize.naturaldelta(delta_uptime)}
**Total Guilds **{len(self.bot.guilds):,}
**Visible Users **{len(self.bot.users):,}
**Memory % **{mem}
{ascii_bar}
            """
            )
        com_msg = self.last_commit_cache['commit']['message']
        embed.add_field(
            name=f'**Latest Commit -** `{self.last_commit_cache["sha"][:7]}`',
            value='\n'.join(['\n'.join(textwrap.wrap(line, 25, break_long_words=False, replace_whitespace=False))
                             for line in com_msg.splitlines() if line.strip() != ''])
        )
        if ctx.author not in self.bot.get_guild(696739356815392779).members:
            embed.add_field(
                name='**Support**',
                value=f'Join the [support server](https://discord.gg/tjq68yq)',
                inline=False)
        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Meta(bot))
