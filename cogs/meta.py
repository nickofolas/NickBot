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
from utils.paginator import ShellMenu, CSMenu


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


class EmbeddedHelpCommand(commands.HelpCommand):
    def __init__(self):
        super().__init__(command_attrs={
            'help': 'Shows help for the bot, a category, or a command.',
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
        embed = discord.Embed(color=discord.Color.main).set_author(name=f'{bot.name} help page')
        description = f'Use `{self.clean_prefix}help <command/category>` for more help\n\n'
        entries = await self.filter_commands(bot.commands, sort=True, key=key)
        for cog, cmds in itertools.groupby(entries, key=key):
            cmds = sorted(cmds, key=lambda c: c.name)
            description += f'**➤ {cog}**\n{" • ".join([c.name for c in cmds])}\n'
        embed.description = description
        await self.context.send(embed=embed)

    async def send_cog_help(self, cog):
        embed = discord.Embed(title=f'{cog.qualified_name} Category', color=discord.Color.main)\
            .set_footer(text='⇶ indicates subcommands')
        description = f'{cog.description or ""}\n\n'
        entries = await self.filter_commands(cog.get_commands(), sort=True)
        description += "\n".join([f'{"⇶" if isinstance(c, commands.Group) else "⇾"} **{c.name}** -'
                                  f' {c.short_doc or "No description"}' for c in entries])
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
        description += "\n".join([f'{"⇶" if isinstance(c, commands.Group) else "⇾"} **{c.name}** -'
                                  f' {c.short_doc or "No description"}' for c in entries])
        embed.description = description
        footer_text = '⇶ indicates subcommands'
        if c := retrieve_checks(group):
            footer_text += f' | Checks: {c}'
        embed.set_footer(text=footer_text)
        await self.context.send(embed=embed)


class Meta(commands.Cog):
    """Commands relating to the bot itself"""

    def __init__(self, bot):
        self.bot = bot
        self.old_help = self.bot.help_command
        self.bot.help_command = EmbeddedHelpCommand()
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

    @commands.command(aliases=['ab', 'info'])
    async def about(self, ctx):
        """Displays info about the bot"""
        appinfo = await self.bot.application_info()
        permissions = discord.Permissions(1878523719)
        invite_url = discord.utils.oauth_url(self.bot.user.id, permissions)
        mem = psutil.virtual_memory()[2]
        vi = sys.version_info
        ascii_bar = utils.data_vis.bar_make(round(mem / 10), 10, fill='▰', empty='▱')
        embed = discord.Embed(color=discord.Color.main)
        embed.set_footer(text=f'Python {vi.major}.{vi.minor}.{vi.micro} | discord.py {discord.__version__}')
        embed.set_author(name=f'Owner: {appinfo.owner}')
        embed.add_field(
            name='**Bot Info**',
            value=f"""
**Current Uptime **{humanize.naturaldelta(self.bot.loop.time())}
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
        links_val = f'[Invite URL]({invite_url})'
        if ctx.author not in self.bot.get_guild(696739356815392779).members:
            links_val += f'\nJoin the [support server](https://discord.gg/tjq68yq)'
        embed.add_field(name='**Links**', value=links_val, inline=False)
        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Meta(bot))
