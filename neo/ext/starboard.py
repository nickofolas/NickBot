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
from typing import Union
from contextlib import suppress

import discord
from discord.ext import commands

import neo
from neo.utils.checks import is_owner_or_administrator

class StarredMessage:
    def __init__(self, bot, *,
                 message_id, channel_id, guild_id,
                 stars=0, sent_msg_id):
        self.bot = bot
        self.message_id = message_id
        self.channel_id = channel_id
        self.guild_id = guild_id
        self.stars = stars
        self.sent_msg_id = sent_msg_id
        self.starboard_channel = self.bot.get_channel(bot.guild_cache[guild_id]['starboard_channel_id'])

    async def __ainit__(self):
        self.message = await self.get_message()
        try:
            self.sent_msg = await self.starboard_channel.fetch_message(self.sent_msg_id)
        except discord.NotFound:
            await self.terminate()
            return None
        await self.bot.pool.execute(
            'INSERT INTO starboard_msgs (message_id, channel_id, '
            'guild_id, stars, sent_msg_id) VALUES ($1, $2, $3, $4, $5)'
            ' ON CONFLICT DO NOTHING',
            self.message_id, self.channel_id, self.guild_id,
            self.stars, self.sent_msg_id,)
        return self

    def __await__(self):
        return self.__ainit__().__await__()

    def __repr__(self):
        return '<{0.__class__.__name__} message_id={0.message_id} ' \
               'stars={0.stars} sent_msg_id={0.sent_msg_id}>'.format(self)

    async def get_message(self):
        return await self.bot.get_channel(self.channel_id)\
            .fetch_message(self.message_id)

    async def update(self, *, new_stars):
        self.stars = new_stars
        if self.stars < self.bot.guild_cache[self.guild_id]['starboard_star_requirement']:
            await self.terminate()
            return
        await self.sent_msg.edit(content=f'⭐ {self.stars}')
        await self.bot.pool.execute(
            'UPDATE starboard_msgs SET stars=$1 WHERE message_id=$2',
            self.stars, self.message_id)

    async def terminate(self):
        with suppress(Exception):
            await self.sent_msg.delete()
            await self.bot.pool.execute(
                'DELETE FROM starboard_msgs WHERE message_id=$1',
                self.message_id)


class Starboard(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.starred = set()
        self.bot.loop.create_task(self.initialise_stars())

    async def cog_check(self, ctx):
        if not ctx.guild: raise commands.CommandError('This category is restricted to guilds')
        if not self.bot.guild_cache[ctx.guild.id]['starboard']:
            raise commands.CommandError('Starboard is not enabled in this guild')
        return True

    @commands.group(name='starboard', invoke_without_command=True)
    @is_owner_or_administrator()
    async def starboard_config(self, ctx):
        """View starboard settings"""
        _config = self.bot.guild_cache[ctx.guild.id]
        if _config['starboard'] is False:
            raise commands.CommandError(
                'Starboard has not been enabled for this guild yet')
        if (ch := _config.get('starboard_channel_id')) is not None:
            star_channel = ctx.guild.get_channel(ch).mention
        else:
            star_channel = 'Not configured'
        description = f'**Starboard Channel** {star_channel}'
        description += '\n**Star Requirement** {}'.format(_config['starboard_star_requirement'])
        embed = neo.Embed(title=f'{ctx.guild}\'s starboard settings',
                          description=description)
        embed.set_thumbnail(url=ctx.guild.icon_url_as(static_format='png'))
        await ctx.send(embed=embed)

    @starboard_config.command(name='set')
    @is_owner_or_administrator()
    async def set_starboard_config(self, ctx, setting, *, new_value: Union[discord.TextChannel, int]):
        """
        Manage starboard settings
        Valid options: `limit`, `channel`
        """
        setting = setting.lower()
        if setting not in (options := ('limit', 'channel')):
            raise commands.CommandError('setting must be one of {}'.format(options))
        query = 'UPDATE guild_prefs SET {}=$1 WHERE guild_id=$2'
        if isinstance(new_value, discord.TextChannel):
            new_value = new_value.id
            setting = 'starboard_channel_id'
        elif isinstance(new_value, int):
            new_value = max(1, new_value) # Disallow values below zero
            setting = 'starboard_star_requirement'
        await self.bot.pool.execute(query.format(setting), new_value, ctx.guild.id)
        await self.bot.guild_cache.refresh()
        await ctx.send('Setting `{0}` successfully changed to `{1}`'.format(setting, new_value))

    async def get_stars(self, payload):
        """Provides a shared functionality to retrieve message 
        objects and their star counts"""
        message = await self.bot.get_channel(payload.channel_id)\
            .fetch_message(payload.message_id)
        try:
            stars = len([*filter(
                lambda u: u.id != message.author.id,
                [u async for u in discord.utils.get(
                    message.reactions, emoji='⭐').users()])])
        except:
            stars = 0
        return message, stars

    def check_star_config(self, payload):
        if not payload.guild_id: return False, None
        predicates = []
        guild = self.bot.guild_cache[payload.guild_id]
        predicates.append(guild['starboard'] is True)
        predicates.append(str(payload.emoji) == '⭐')
        predicates.append(guild['starboard_channel_id'] is not None)
        predicates.append(payload.channel_id != guild['starboard_channel_id'])
        return all(predicates), guild

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        """Sends starred messages and increases their counts"""
        checked, guild = self.check_star_config(payload)
        if not checked: return
        message, stars = await self.get_stars(payload)
        if payload.user_id == message.author.id: return
        if (existing := discord.utils.get(self.starred, message_id=payload.message_id)):
            await existing.update(new_stars = stars)
            return
        if stars >= guild['starboard_star_requirement']:
            embed = neo.Embed(
                timestamp=message.created_at,
                description=message.content)
            embed.set_author(
                name=str(message.author),
                icon_url=message.author.avatar_url_as(static_format='png'))
            if message.attachments:
                for attach in message.attachments:
                    embed.add_field(
                        name='Attachment',
                        value=f'[URL]({attach.url})')
                embed.set_image(url=message.attachments[-1].url)
            embed.add_field(name='Jump', value=f'[URL]({message.jump_url})', inline=False)
            sent = await self.bot.get_channel(guild['starboard_channel_id']).send(
                f'⭐ {stars}',
                embed=embed)
            self.starred.add(await StarredMessage(
                self.bot, message_id = message.id,
                channel_id = message.channel.id,
                guild_id = message.guild.id,
                stars = stars, sent_msg_id = sent.id))

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        """Decreases and terminates starred message counts"""
        checked, guild = self.check_star_config(payload)
        if not checked: return
        message, stars = await self.get_stars(payload)
        if payload.user_id == message.author.id: return
        if (star := discord.utils.get(self.starred, message_id=payload.message_id)):
            await star.update(new_stars = stars)
        if stars < guild['starboard_star_requirement']:
            self.starred.discard(star)

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload):
        if (star := discord.utils.get(self.starred, message_id=payload.message_id)):
            await star.terminate()
            self.starred.discard(star)

    @commands.Cog.listener()
    async def on_raw_bulk_message_delete(self, payload):
        for msg_id in payload.message_ids:
            if (star := discord.utils.get(self.starred, message_id=msg_id)):
                await star.terminate()
                self.starred.discard(star)


    async def initialise_stars(self):
        await self.bot.wait_until_ready()
        for record in await self.bot.pool.fetch('SELECT * FROM starboard_msgs'):
            self.starred.add(await StarredMessage(self.bot, **dict(record)))


def setup(bot):
    bot.add_cog(Starboard(bot))
