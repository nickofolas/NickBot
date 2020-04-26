import asyncio
from datetime import datetime
import re
import argparse
import shlex

import aiosqlite as asq
import discord
from discord.ext import commands
from discord.ext.commands import has_permissions
import humanize


class Arguments(argparse.ArgumentParser):
    def error(self, message):
        raise RuntimeError(message)


ereg = re.compile(
    r'(<a?:\w*:\d*>)|([\U00002600-\U000027BF])|([\U0001f300-\U0001f64F])|([\U0001f680-\U0001f6FF])'
)

units = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}


class Mods(commands.Cog):
    """Moderation commands, can only be used in a guild"""

    def __init__(self, bot):
        self.bot = bot

    def cog_check(self, ctx):
        if ctx.guild:
            return True
        else:
            return False

    # Channel lock command
    @commands.command(aliases=['l'])
    @has_permissions(manage_channels=True, manage_messages=True)
    async def lock(self, ctx):
        """Lock the current channel"""
        await ctx.channel.set_permissions(
            ctx.guild.default_role, send_messages=False)
        lock = discord.Embed(
            title='Channel Locked',
            description='This channel has been locked until further notice',
            color=discord.Color.main)
        await ctx.send(embed=lock)

    # Channel unlock command
    @commands.command(aliases=['ul'])
    @has_permissions(manage_channels=True, manage_messages=True)
    async def unlock(self, ctx):
        """Unlock a locked channel"""
        await ctx.channel.set_permissions(
            ctx.guild.default_role, overwrite=None)
        unlock = discord.Embed(
            title='Channel Unlocked',
            description='This channel is now unlocked',
            color=discord.Color.main)
        await ctx.send(embed=unlock)

    # Bulk clear command
    @commands.group(aliases=['c', 'purge'], invoke_without_command=True)
    @has_permissions(manage_messages=True)
    async def clear(self, ctx, amount: int = 1):
        """Bulk clear a specified amount of messages"""
        if ctx.invoked_subcommand is None:
            await ctx.message.delete()
            await ctx.channel.purge(limit=amount)

    @clear.command(aliases=['emj'])
    @has_permissions(manage_messages=True)
    async def emoji(self, ctx, amount: int):
        """Clear messages with emoji from the channel"""
        custom_emoji = re.compile(
            r'(<a?:\w*:\d*>)|([\U00002600-\U000027BF])|([\U0001f300-\U0001f64F])|([\U0001f680-\U0001f6FF])'
        )
        await ctx.message.delete()
        await ctx.channel.purge(
            limit=amount, check=lambda m: custom_emoji.search(m.content))

    @clear.command(aliases=['fi', 'file'])
    @has_permissions(manage_messages=True)
    async def files(self, ctx, amount: int):
        """Clears the specified number of files from the channel"""
        await ctx.message.delete()
        await ctx.channel.purge(limit=amount, check=lambda m: m.attachments)

    @clear.command()
    @has_permissions(manage_messages=True)
    async def bot(self, ctx, amount: int):
        """Clears a given amount of messages from bots"""
        await ctx.message.delete()
        await ctx.channel.purge(limit=amount, check=lambda m: m.author.bot)

    @clear.command()
    @has_permissions(manage_messages=True)
    async def user(self, ctx, amount: int, *, user: discord.Member):
        """Clear messages from a given user"""
        await ctx.message.delete()
        await ctx.channel.purge(limit=amount, check=lambda m: m.author == user)

    @clear.command(aliases=['keyword', 'k'])
    @has_permissions(manage_messages=True)
    async def kw(self, ctx, amount: int, *, keyword: str):
        """Clear only messages with specified keyword(s)"""
        await ctx.message.delete()
        await ctx.channel.purge(
            limit=amount, check=lambda m: keyword in m.content)

    @clear.command()
    @has_permissions(manage_messages=True)
    async def code(self, ctx, amount: int):
        """Clear messages with codeblocks"""
        await ctx.message.delete()
        await ctx.channel.purge(
            limit=amount, check=lambda m: '```' in m.content)

    @clear.command()
    @has_permissions(manage_messages=True)
    async def regex(self, ctx, amount: int, *, regex):
        """Clear messages based off an inputted regex"""
        custom_regex = re.compile(regex)
        await ctx.message.delete()
        await ctx.channel.purge(
            limit=amount, check=lambda m: custom_regex.search(m.content))

    async def do_removal(self,
                         ctx,
                         limit,
                         predicate,
                         *,
                         before=None,
                         after=None):
        if limit > 2000:
            return await ctx.send(
                f'Too many messages to search given ({limit}/2000)')

        if before is None:
            before = ctx.message
        else:
            before = discord.Object(id=before)

        if after is not None:
            after = discord.Object(id=after)
        await ctx.channel.purge(
            limit=limit, before=before, after=after, check=predicate)

    @clear.command(aliases=['-c', 'cu', 'adv'])
    @has_permissions(manage_messages=True)
    async def custom(self, ctx, *, args: str):
        """
        Advanced clear command that takes any combination of args
        `--user|--contains|--starts|--ends|--search|--after|--before`
        Flag options (no arguments):
        `--bot|--embeds|--files|--emoji|--reactions|--or|--not|--nohide|--code`
        """
        parser = Arguments(add_help=False, allow_abbrev=False)
        parser.add_argument('--user', nargs='+')
        parser.add_argument('--contains', nargs='+')
        parser.add_argument('--regex')
        parser.add_argument('--starts', nargs='+')
        parser.add_argument('--ends', nargs='+')
        parser.add_argument('--or', action='store_true', dest='_or')
        parser.add_argument('--not', action='store_true', dest='_not')
        parser.add_argument('--emoji', action='store_true')
        parser.add_argument('--nohide', action='store_true')
        parser.add_argument(
            '--bot', action='store_const', const=lambda m: m.author.bot)
        parser.add_argument(
            '--embeds', action='store_const', const=lambda m: len(m.embeds))
        parser.add_argument(
            '--code', action='store_true')
        parser.add_argument(
            '--files',
            action='store_const',
            const=lambda m: len(m.attachments))
        parser.add_argument(
            '--reactions',
            action='store_const',
            const=lambda m: len(m.reactions))
        parser.add_argument('--search', type=int, default=5)
        parser.add_argument('--after', type=int)
        parser.add_argument('--before', type=int)

        try:
            args = parser.parse_args(shlex.split(args))
        except Exception as e:
            await ctx.send(str(e))
            return

        predicates = []
        if args.bot:
            predicates.append(args.bot)

        if args.embeds:
            predicates.append(args.embeds)

        if args.files:
            predicates.append(args.files)

        if args.reactions:
            predicates.append(args.reactions)

        if args.emoji:
            custom_emoji = re.compile(
                r'(<a?:\w*:\d*>)|([\U00002600-\U000027BF])|([\U0001f300-\U0001f64F])|([\U0001f680-\U0001f6FF])'
            )
            predicates.append(lambda m: custom_emoji.search(m.content))

        if args.regex:
            custom_regex = re.compile(args.regex)
            predicates.append(lambda m, x=custom_regex: x.search(m.content))

        if args.code:
            predicates.append(lambda m: '```' in m.content)

        if args.user:
            users = []
            converter = commands.MemberConverter()
            for u in args.user:
                try:
                    user = await converter.convert(ctx, u)
                    users.append(user)
                except Exception as e:
                    await ctx.send(str(e))
                    return

            predicates.append(lambda m: m.author in users)

        if args.contains:
            predicates.append(
                lambda m: any(sub in m.content for sub in args.contains))

        if args.starts:
            predicates.append(
                lambda m: any(m.content.startswith(s) for s in args.starts))

        if args.ends:
            predicates.append(
                lambda m: any(m.content.endswith(s) for s in args.ends))

        op = all if not args._or else any

        def predicate(m):
            r = op(p(m) for p in predicates)
            if args._not:
                return not r
            return r

        args.search = max(0, min(2000, args.search))  # clamp from 0-2000
        if not args.nohide:
            await ctx.message.delete()
        await self.do_removal(
            ctx, args.search, predicate, before=args.before, after=args.after)

    @clear.command(
        aliases=['reactionclear', 'rc', 'reactions', 'r'], )
    @has_permissions(manage_messages=True)
    async def rclear(self, ctx, amount: int):
        """Clears all reactions from the specified number of messages"""
        await ctx.message.delete()
        async for message in ctx.channel.history(limit=amount):
            await message.clear_reactions()

    # Mute command
    @commands.group(invoke_without_command=True)
    @has_permissions(manage_messages=True)
    async def mute(self,
                   ctx,
                   member: discord.Member,
                   duration: int = None,
                   time_unit: str = None):
        """Apply an indefinite or temporary mute on a member"""
        if duration is None and time_unit is None:
            role = discord.utils.get(ctx.guild.roles, name="Muted")
            await member.add_roles(role)
            await ctx.message.delete()
        else:
            role = discord.utils.get(ctx.guild.roles, name="Muted")
            await member.add_roles(role)
            await ctx.message.delete()
            # Send notif if in specified channel
            if ctx.guild.id == 626080674474098697:
                embed = discord.Embed(
                    description=
                    f'{member} muted for {duration} {time_unit} by {ctx.author}',
                    color=discord.Color.main)
                embed.set_author(name=member)
                embed.set_thumbnail(
                    url=str(member.avatar_url).replace("webp", "png"))
                notifs = self.bot.get_channel(655891096253104149)
                await notifs.send(embed=embed)
            # Sleeps for specified amount of time
            await asyncio.sleep(duration * units[time_unit[:1]])
            await member.remove_roles(role)

    @mute.command()
    @has_permissions(administrator=True)
    async def update(self, ctx):
        """Update channel perms to add mute role"""
        muterole = discord.utils.get(ctx.guild.roles, name="Muted")
        try:
            await ctx.message.add_reaction('<a:loading:681628799376293912>')
            for channel in ctx.guild.channels:
                await channel.set_permissions(
                    muterole, send_messages=False, add_reactions=False)
            await ctx.message.clear_reactions()
            await ctx.send('Successfully updated channels')
        except Exception:
            pass

    # Manual unmute command
    @commands.command()
    @has_permissions(manage_messages=True)
    async def unmute(self, ctx, member: discord.Member):
        """Unmute a muted user"""
        role = discord.utils.get(ctx.guild.roles, name="Muted")
        # Checks if specified user is muted
        if role in member.roles:
            await member.remove_roles(role)
            await ctx.message.delete()
            if ctx.guild.id == 626080674474098697:
                embed = discord.Embed(
                    description=f'{member} unmuted manually by {ctx.author}',
                    color=0x2cff00)
                embed.set_author(name=member)
                embed.set_thumbnail(
                    url=str(member.avatar_url).replace("webp", "png"))
                notifs = self.bot.get_channel(655891096253104149)
                await notifs.send(embed=embed)
        # If user is not muted
        else:
            embed = discord.Embed(
                description=f'{member} is not currently muted',
                color=discord.Color.main)
            embed.set_author(name=member)
            embed.set_thumbnail(
                url=str(member.avatar_url).replace("webp", "png"))
            sembed = await ctx.send(embed=embed)
            await asyncio.sleep(5)
            await sembed.delete()

    @commands.command()
    @has_permissions(ban_members=True)
    async def ban(self, ctx, member: discord.Member, *, reason=None):
        """Issue a permanent ban - optional reason"""
        try:
            await member.send(
                f'You have been permanently banned in the {ctx.guild} server. Reason: **{reason}**'
            )
        except Exception:
            pass
        await member.ban(reason=reason)
        await ctx.send(f'{member} was permanently banned - **{reason}**')
        await ctx.message.delete()

    @commands.command()
    @has_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member, *, reason=None):
        """Kick a member - optional reason can be provided"""
        await member.send(
            f'You have been kicked from the {ctx.guild} server. Reason: **{reason}**'
        )
        await member.kick(reason=reason)
        await ctx.send(f'{member} was kicked - **{reason}**')
        await ctx.message.delete()

    @commands.group()
    @has_permissions(administrator=True)
    async def role(self, ctx):
        """Command group to work with roles"""

    ''' Removed for API abuse concerns
    @role.command()
    @has_permissions(administrator=True)
    async def all(self, ctx, role: discord.Role):
      """Apply a role to every member in the guild"""
      for mem in ctx.guild.members:
        await mem.add_roles(role)
      embed = discord.Embed(title=' ', description=f'Successfully applied role {role.mention} to all members of the guild')
      await ctx.send(embed=embed)
    '''

    @role.command()
    @has_permissions(administrator=True)
    async def member(self, ctx, role: discord.Role, user: discord.Member):
        """Apply a role to a specific member"""
        await user.add_roles(role)
        embed = discord.Embed(
            title=' ',
            description=
            f'Successfully applied role {role.mention} to {user.mention}')
        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Mods(bot))
