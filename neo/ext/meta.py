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
from difflib import get_close_matches

import discord
import humanize
import psutil
from discord.ext import commands

import neo
from neo.utils.formatters import flatten

(checked_perms := ['is_owner', 'guild_only', 'dm_only', 'is_nsfw']) \
    .extend(dict(discord.Permissions()).keys())


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
        self.subcommand_not_found = self.command_not_found

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
            return c.cog_name or '\u200bUncategorised'

        bot = self.context.bot
        embed = neo.Embed(title=f'{bot.user.name} Help')
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
        embed = neo.Embed(title=f'{cog.qualified_name} Category')
        description = f'{cog.description or ""}\n\n'
        entries = await self.filter_commands(cog.get_commands(), sort=True)
        self.cog_group_common_fmt(embed, description, entries)
        await self.context.send(embed=embed)

    async def send_group_help(self, group):
        embed = neo.Embed(title=self.get_command_signature(group))
        description = f'{group.help or "No description provided"}\n\n'
        entries = await self.filter_commands(group.commands, sort=True)
        self.cog_group_common_fmt(embed, description, entries)
        footer = embed.footer.text
        if c := retrieve_checks(group):
            footer += f' | Checks: {c}'
        embed.set_footer(text=footer)
        await self.context.send(embed=embed)

    async def send_command_help(self, command):
        embed = neo.Embed(title=self.get_command_signature(command))
        description = f'{command.help or "No description provided"}\n\n'
        embed.description = description
        if c := retrieve_checks(command):
            embed.set_footer(text=f'Checks: {c}')
        await self.context.send(embed=embed)

    def command_not_found(self, *args):
        invalid_input_string = ' '.join(map(str, args))
        offered_commands = (cmd.qualified_name for cmd in self.context.bot.walk_commands())
        return get_close_matches(invalid_input_string, offered_commands) or invalid_input_string

    async def send_error_message(self, error):
        if isinstance(error, list):
            suggestions = '\n⇾ '.join(error)
            embed = neo.Embed(title='Did you mean...')
            embed.description = f'⇾ {suggestions}'
            return await self.context.send(embed=embed)
        elif isinstance(error, str):
            return await self.context.send(
                f'No command named \'{error}\', and no similarly named commands found')
        else:
            await super().send_error_message(error)



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
        """Show source for a command or the entire bot"""
        desc = str()
        cmd = self.bot.get_command(cmd) if cmd else None
        if not cmd:
            title = 'View full source'
            url = 'https://github.com/nickofolas/neo'
        else:
            if isinstance(cmd, self.bot.help_command._command_impl.__class__):
                c = type(self.bot.help_command)
                fpath = os.path.relpath(inspect.getsourcefile(c))
            else:
                c = cmd.callback
                fpath = os.path.relpath(c.__code__.co_filename)
            lines, first_ln = inspect.getsourcelines(c)
            last_ln = first_ln + (len(lines) - 1)
            title = f'View source for command {cmd.qualified_name}'
            url = f'https://github.com/nickofolas/neo/blob/master/{fpath}#L{first_ln}-L{last_ln}'
            desc += f'**File** {fpath}\n**Lines** {first_ln} - {last_ln} [{len(lines) - 1} total]\n\n'
        desc += f'{neo.conf["emojis"]["github"]["star"]} the repository to support neo\'s development!'
        await ctx.send(embed=neo.Embed(title=title, description=desc, url=url))

    async def fetch_latest_commit(self):
        headers = {'Authorization': f'token  {neo.secrets.github_token}'}
        url = 'https://api.github.com/repos/nickofolas/neo/commits'
        async with self.bot.session.get(f'{url}/master', headers=headers) as resp1:
            self.last_commit_cache = await resp1.json()

    @commands.command(aliases=['ab', 'info', 'support'])
    async def about(self, ctx):
        """Displays info about the bot"""
        appinfo = await self.bot.application_info()
        permissions = discord.Permissions(1878523719)
        invite_url = discord.utils.oauth_url(self.bot.user.id, permissions)
        mem = psutil.virtual_memory()[2]
        vi = sys.version_info
        embed = neo.Embed().set_thumbnail(url=self.bot.user.avatar_url_as(
            static_format='png'))
        embed.set_footer(text=f'Python {vi.major}.{vi.minor}.{vi.micro} | discord.py {discord.__version__}')
        embed.set_author(name=f'Owner: {appinfo.team.owner}', icon_url=appinfo.team.owner.avatar_url_as(static_format='png'))
        embed.add_field(
            name='**Bot Info**',
            value=textwrap.dedent(f"""
                **Current Uptime **{humanize.naturaldelta(self.bot.loop.time())}
                **Total Guilds **{len(self.bot.guilds):,}
                **Visible Users **{len(self.bot.users):,}
                **Memory **{mem}%
            """))
        com_url = self.last_commit_cache['html_url']
        com_id_brief = self.last_commit_cache["sha"][:7]
        links = list()
        if ctx.author not in self.bot.get_guild(696739356815392779).members:
            links.append(f'[Support](https://discord.gg/tjq68yq)')
        links.extend((f'[Invite]({invite_url})', f'[`{com_id_brief}`]({com_url})'))
        embed.add_field(name='**Links**', value=' | '.join(links), inline=False)
        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Meta(bot))
