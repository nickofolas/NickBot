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
import inspect
import itertools
import os
import sys
import textwrap
from contextlib import suppress

import discord
import humanize
import psutil
from discord.ext import commands

from utils.config import conf

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
            'help': 'Shows help for the bot, a category, or a command.'
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
        embed = discord.Embed(title=f'{bot.user.name} Help', color=discord.Color.main)
        description = f'Use `{self.clean_prefix}help <command/category>` for more help\n\n'
        entries = await self.filter_commands(bot.commands, sort=True, key=key)
        for cog, cmds in itertools.groupby(entries, key=key):
            cmds = sorted(cmds, key=lambda c: c.name)
            description += f'**➣ {cog}**\n{" • ".join([c.name for c in cmds])}\n'
        embed.description = description
        await self.context.send(embed=embed)

    @staticmethod
    def cog_group_common_fmt(embed, description, entries):
        description += "\n".join([f'{"⇶" if isinstance(c, commands.Group) else "⇾"} **{c.name}** -'
                                  f' {c.short_doc or "No description"}' for c in entries])
        embed.set_footer(text='⇶ indicates subcommands')
        embed.description = description

    async def send_cog_help(self, cog):
        embed = discord.Embed(title=f'{cog.qualified_name} Category', color=discord.Color.main)
        description = f'{cog.description or ""}\n\n'
        entries = await self.filter_commands(cog.get_commands(), sort=True)
        self.cog_group_common_fmt(embed, description, entries)
        await self.context.send(embed=embed)

    async def send_group_help(self, group):
        embed = discord.Embed(title=self.get_command_signature(group), color=discord.Color.main)
        description = f'{group.help or "No description provided"}\n\n'
        entries = await self.filter_commands(group.commands, sort=True)
        self.cog_group_common_fmt(embed, description, entries)
        footer = embed.footer.text
        if c := retrieve_checks(group):
            footer += f' | Checks: {c}'
        embed.set_footer(text=footer)
        await self.context.send(embed=embed)

    async def send_command_help(self, command):
        embed = discord.Embed(title=self.get_command_signature(command), color=discord.Color.main)
        description = f'{command.help or "No description provided"}\n\n'
        embed.description = description
        if c := retrieve_checks(command):
            embed.set_footer(text=f'Checks: {c}')
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

    @commands.command(aliases=['src'])
    async def source(self, ctx, *, cmd=None):
        if cmd is None:
            return await ctx.send('<https://github.com/nickofolas/neo>')
        c = self.bot.get_command(cmd).callback
        file = c.__code__.co_filename
        location = os.path.relpath(file)
        lines, first_line = inspect.getsourcelines(c)
        last_line = first_line + (len(lines) - 1)
        await ctx.send(f'<https://github.com/nickofolas/neo/blob/master/{location}#L{first_line}-L{last_line}>')

    async def fetch_latest_commit(self):
        headers = {'Authorization': f'token  {os.getenv("GITHUB_TOKEN")}'}
        url = 'https://api.github.com/repos/nickofolas/neo/commits'
        async with self.bot.session.get(f'{url}/master', headers=headers) as resp1:
            # noinspection PyAttributeOutsideInit
            self.last_commit_cache = await resp1.json()

    @commands.command(aliases=['ab', 'info'])
    async def about(self, ctx):
        """Displays info about the bot"""
        appinfo = await self.bot.application_info()
        permissions = discord.Permissions(1878523719)
        invite_url = discord.utils.oauth_url(self.bot.user.id, permissions)
        mem = psutil.virtual_memory()[2]
        vi = sys.version_info
        embed = discord.Embed(color=discord.Color.main).set_thumbnail(url=self.bot.user.avatar_url_as(
            static_format='png'))
        embed.set_footer(text=f'Python {vi.major}.{vi.minor}.{vi.micro} | discord.py {discord.__version__}')
        embed.set_author(name=f'Owner: {appinfo.owner}', icon_url=appinfo.owner.avatar_url_as(static_format='png'))
        embed.add_field(
            name='**Bot Info**',
            value=textwrap.dedent(f"""
                **Current Uptime **{humanize.naturaldelta(self.bot.loop.time())}
                **Total Guilds **{len(self.bot.guilds):,}
                **Visible Users **{len(self.bot.users):,}
                **Memory **{mem}%
            """)
        )
        com_url = self.last_commit_cache['html_url']
        com_id_brief = self.last_commit_cache["sha"][:7]
        links_val = f'**Invite neo** [Invite URL]({invite_url})'
        if ctx.author not in self.bot.get_guild(696739356815392779).members:
            links_val += f'\n**Support Server** [Join Here](https://discord.gg/tjq68yq)'
        links_val += f'\n**Latest Commit** [`{com_id_brief}`]({com_url})'
        embed.add_field(name='**Links**', value=links_val, inline=False)
        await ctx.send(embed=embed)

    @commands.command(name='license', aliases=['copyright'])
    async def _view_license(self, ctx):
        """View neo's license"""
        await ctx.send(embed=discord.Embed(description=conf['license'], color=discord.Color.main))


def setup(bot):
    bot.add_cog(Meta(bot))
