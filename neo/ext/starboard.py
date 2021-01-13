import asyncio
import textwrap
from datetime import datetime
from typing import Union

import discord
from discord.ext import commands


MEDALS = ("🥇", "🥈", "🥉", "\n4", "5")


class Star:
    def __init__(self, *, referencing_message, original_id, stars=0):
        self.original_id = original_id
        self.referencing_message = referencing_message
        self.stars = stars

    def __repr__(self):
        return (
            "<{0.__class__.__name__} stars={0.stars} "
            "original_id={0.original_id}>".format(self)
        )

    def to_composite_castable(self):
        copy = vars(self).copy()
        copy.update(referencing_message=self.referencing_message.id)
        return copy

    async def edit(self, **kwargs):
        await self.referencing_message.edit(**kwargs)


class Starboard:
    def __init__(
        self, *, channel: discord.TextChannel, stars, format, required_stars, max_days
    ):
        self.channel = channel
        self.required_stars = required_stars
        self.max_days = max_days
        self._stars = stars
        self._cached_stars = {}
        self._format = format
        self._ready = False

    def __await__(self):
        return self.__ainit__().__await__()

    async def __ainit__(self):
        for star in self._stars:

            try:
                message = self.channel.get_partial_message(star["starred_message_id"])

            except Exception as e:
                print(e)
                continue

            self._cached_stars[star["message_id"]] = Star(
                referencing_message=message,
                stars=star["stars"],
                original_id=star["message_id"],
            )

        self._ready = True
        return self

    @property
    def stars(self):
        return self._cached_stars

    def get_star(self, id):
        return self._cached_stars.get(id)

    async def create_star(self, message, stars):
        if not self._ready:
            return
        if self.get_star(message.id):
            return

        kwargs = {"original_id": message.id, "stars": stars}

        embed = discord.Embed(description=str())
        embed.set_author(name=message.author, icon_url=message.author.avatar_url)
        if message.content:
            embed.description = (
                message.content[:1897] + "..."
                if len(message.content) >= 1900
                else message.content
            )
            embed.description += "\n\n"
        embed.description += f"**[Jump URL]({message.jump_url})**"

        for attachment in (*message.attachments, *message.embeds):
            if not embed.image:
                embed.set_image(url=attachment.url)
            embed.add_field(
                name=discord.utils.escape_markdown(
                    getattr(attachment, "filename", "Embed")
                ),
                value="[View]({.url})".format(attachment),
            )

        referencing = await self.channel.send(
            content=self._format.format(stars=stars), embed=embed
        )
        kwargs["referencing_message"] = referencing

        star = Star(**kwargs)
        self._cached_stars[star.original_id] = star
        return star

    async def destroy_star(self, id):
        if not self._ready:
            return

        star = self._cached_stars.pop(id)
        try:
            await star.referencing_message.delete()
        finally:
            return star

    async def update_star(self, id, stars):
        if not self._ready:
            return

        star = self.get_star(id)
        star.stars = stars

        content = self._format.format(stars=star.stars)
        await star.edit(content=content)

        return star


class StarboardCog(commands.Cog, name="Starboard"):
    def __init__(self, bot):
        self.bot = bot
        self._ready = False
        self.starboards = {}
        bot.loop.create_task(self.__ainit__())

    async def __ainit__(self):
        await self.bot.wait_until_ready()

        for guild, config in self.bot.guild_cache.items():
            if not config.get("starboard_channel_id"):
                continue

            query = """
            SELECT message_id, stars, starred_message_id
            FROM starboard_msgs
            WHERE guild_id = $1
            """

            starred_messages = await self.bot.pool.fetch(query, guild)
            kwargs = {
                "channel": self.bot.get_channel(config["starboard_channel_id"]),
                "stars": starred_messages,
                "format": config["starboard_format"],
                "required_stars": config["starboard_star_requirement"],
                "max_days": config["starboard_max_days"],
            }

            self.starboards[guild] = Starboard(**kwargs)

        await asyncio.gather(*self.starboards.values())

        self._ready = True

    async def get_message(self, channel, message_id):
        message = await channel.history(
            limit=1, before=discord.Object(message_id + 1)
        ).next()
        return message

    def reaction_check(self, payload):
        return str(payload.emoji) == "⭐"

    @commands.Cog.listener("on_raw_reaction_add")
    @commands.Cog.listener("on_raw_reaction_remove")
    @commands.Cog.listener("on_raw_reaction_clear")
    @commands.Cog.listener("on_raw_reaction_clear_emoji")
    @commands.Cog.listener("on_raw_message_delete")
    async def handle_star_changes(self, payload):
        if not (starboard := self.starboards.get(payload.guild_id)):
            return
        if not starboard._ready:
            return
        if not self.bot.guild_cache[payload.guild_id].get("starboard", False):
            return
        if payload.channel_id == starboard.channel.id:
            return
        if (
            datetime.utcnow() - discord.Object(payload.message_id).created_at
        ).days > starboard.max_days:
            return

        if (star := starboard.get_star(payload.message_id)) is None:

            message = await self.get_message(
                self.bot.get_channel(payload.channel_id), payload.message_id
            )

            count = getattr(
                discord.utils.get(message.reactions, emoji="\N{WHITE MEDIUM STAR}"),
                "count",
                0,
            )
            if count < starboard.required_stars:
                return

            star = await starboard.create_star(message, count)

            if not star:
                return

            query = """
            INSERT INTO starboard_msgs (
                message_id, 
                channel_id, 
                guild_id, 
                stars, 
                starred_message_id
            )
            VALUES ($1,$2,$3,$4,$5)
            """
            arguments = (
                message.id,
                message.channel.id,
                message.guild.id,
                count,
                star.referencing_message.id,
            )
            await self.bot.pool.execute(query, *arguments)

        else:

            if isinstance(payload, discord.RawReactionActionEvent):
                if not self.reaction_check(payload):
                    return

                if payload.event_type == "REACTION_ADD":
                    star.stars += 1
                else:
                    star.stars -= 1

            elif isinstance(payload, discord.RawReactionClearEmojiEvent):
                if not self.reaction_check(payload):
                    return
                star.stars = 0

            elif isinstance(
                payload, (discord.RawReactionClearEvent, discord.RawMessageDeleteEvent)
            ):
                star.stars = 0

            if star.stars < starboard.required_stars:
                await starboard.destroy_star(star.original_id)
                query = "DELETE FROM starboard_msgs WHERE message_id = $1"
                await self.bot.pool.execute(query, star.original_id)
            else:
                await starboard.update_star(star.original_id, star.stars)
                query = """
                UPDATE starboard_msgs
                SET stars = $1
                WHERE message_id = $2
                """
                await self.bot.pool.execute(query, star.stars, star.original_id)

    @commands.group(invoke_without_command=True)
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    async def starboard(self, ctx):
        if not (starboard := self.starboards.get(ctx.guild.id)):
            raise commands.BadArgument(
                "Starboard has not been enabled for this guild yet"
            )

        embed = discord.Embed(title=f"{ctx.guild}'s starboard settings")
        embed.description = textwrap.dedent(
            """
        **Starboard Channel** {0.channel.mention}
        **Star Requirement** {0.required_stars:,d}
        **Max Days** {0.max_days:,d}
        **Format**: {0._format}

        """.format(
                starboard
            )
        )
        await ctx.send(embed=embed)

    @starboard.command(aliases=["lb"])
    @commands.guild_only()
    async def leaderboard(self, ctx):
        if ctx.guild.id not in self.starboards:
            raise commands.CommandError("This server doesn't have a starboard!")

        starboard = self.starboards.get(ctx.guild.id)

        embed = discord.Embed(title=f"{ctx.guild} Starboard Leaderboard", description="")

        top_stars = sorted(
            starboard.stars.values(), key=lambda star: star.stars, reverse=True
        )

        for index, star in enumerate(top_stars):
            try:
                embed.description += "{0} [{1.stars} stars]({1.referencing_message.jump_url})\n".format(
                    MEDALS[index], star
                )
            
            except IndexError:
                break

        await ctx.send(embed=embed)

    @starboard.command()
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def create(self, ctx, *, channel: Union[discord.TextChannel, str] = None):
        if ctx.guild.id in self.starboards:
            raise commands.BadArgument(
                "You already have a starboard, use `change` to set your starboard to a different channel"
            )

        if channel is None:
            channel = "starboard"

        overwrites = {
            ctx.guild.default_role: discord.PermissionOverwrite(send_messages=False),
            ctx.guild.me: discord.PermissionOverwrite(send_messages=True),
        }
        if isinstance(channel, str):
            channel = await ctx.guild.create_text_channel(
                name=channel, overwrites=overwrites, category=ctx.channel.category
            )
        else:
            await channel.edit(overwrites=overwrites)

        query = """
        UPDATE guild_prefs
        SET starboard_channel_id = $1
        WHERE guild_id = $2
        RETURNING *;
        """
        row = await self.bot.pool.fetchrow(query, channel.id, ctx.guild.id)

        starboard = await Starboard(
            channel=channel,
            stars=[],
            format=row["starboard_format"],
            required_stars=row["starboard_star_requirement"],
            max_days=row["starboard_max_days"],
        )
        self.starboards[ctx.guild.id] = starboard
        self.bot.guild_cache[ctx.guild.id].update(dict(row))
        await ctx.send(
            f"Created starboard which resides at {starboard.channel.mention}"
        )

    @starboard.command()
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def change(self, ctx, *, channel: discord.TextChannel = None):
        if ctx.guild.id not in self.starboards:
            raise commands.BadArgument(
                "You don't have a preexisting starboard, use `create` instead!"
            )

        result = await ctx.prompt(
            "This will invalidate all existing starred messages. Are you sure you want to relocate/disband the starboard?"
        )
        if not result:
            return await ctx.send("Exiting")
        if isinstance(channel, discord.TextChannel):
            overwrites = {
                ctx.guild.default_role: discord.PermissionOverwrite(
                    send_messages=False
                ),
                ctx.guild.me: discord.PermissionOverwrite(send_messages=True),
            }
            await channel.edit(overwrites=overwrites)

        self.starboards[ctx.guild.id].channel = channel
        channel = getattr(channel, "id", channel)
        await self.bot.pool.execute(
            "SELECT change_starboard($1, $2); ", channel, ctx.guild.id
        )

        self.bot.guild_cache[ctx.guild.id].update({"starboard_channel_id": channel})
        if channel:
            await ctx.send("Starboard relocated")
        else:
            self.starboards.pop(ctx.guild.id)
            await ctx.send("Starboard has been disbanded")

    @starboard.command(name="set")
    async def _set(self, ctx, key: str, *, value: Union[discord.TextChannel, int, str]):
        if key not in (allowed_keys := ("star_requirement", "format", "max_days")):
            raise commands.BadArgument(
                f"Key must be one of {', '.join(list(allowed_keys))}"
            )
        value = getattr(value, "id", value)

        query = """
        UPDATE guild_prefs
        SET starboard_{0} = $1
        WHERE guild_id = $2
        RETURNING *;
        """
        ret = await self.bot.pool.fetchrow(query.format(key), value, ctx.guild.id)
        self.bot.guild_cache[ctx.guild.id] = dict(ret)

        starboard = self.starboards[ctx.guild.id]
        if key == "star_requirement":
            starboard.required_stars = value

        elif key == "format":
            starboard._format = value
        elif key == "max_days":
            starboard.max_days = value

        await ctx.send(f"Setting `{key}` successfully changed to `{value}`")


def setup(bot):
    bot.add_cog(StarboardCog(bot))
