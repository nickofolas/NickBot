import re

from discord.ext import commands
import discord


class Context(commands.Context):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    async def prompt(self, message):
        emojis = {
            '<:c_:703740667926675536>': True,
            '<:x_:703739402094117004>': False}
        msg = await self.send(message)
        for e in emojis.keys():
            await msg.add_reaction(e)
        payload = await self.bot.wait_for(
            'raw_reaction_add',
            check=lambda p: str(p.emoji) in emojis.keys()
            and p.user_id == self.author.id and p.message_id == msg.id)
        if emojis[str(payload.emoji)] is True:
            await msg.edit(content='Confirmed!')
            return True
        else:
            await msg.edit(content='Cancelled!')
            return False

    async def safe_send(self, content=None, **kwargs):
        if content:
            if match := re.search(re.compile(r'([a-zA-Z0-9]{24}\.[a-zA-Z0-9]{6}\.[a-zA-Z0-9_\-]{27}|mfa\.[a-zA-Z0-9_\-]{84})'), content):
                content = content.replace(match.group(0), '[token omitted]')
            if len(content) > 2000:
                async with self.bot.session.post(
                        "https://mystb.in/documents",
                        data=content.encode('utf-8')) as post:
                    post = await post.json()
                    url = f"https://mystb.in/{post['key']}"
                    await self.send(
                        f'The output was too long for discord, so it can'
                        f' be found here: <{url}>'
                    )
            else:
                return await self.send(content, **kwargs)
        else:
            await self.send(**kwargs)

    def tick(self, opt, label=None):
        lookup = {
            True: '<:c_:703740667926675536>',
            False: '<:x_:703739402094117004>',
            None: '<:unicode_neutral:704141512912666624>',
        }
        emoji = lookup.get(opt, '<:x_:703739402094117004>')
        if label is not None:
            return f'{emoji}: {label}'
        return emoji

    def tab(self, repeat=1):
        tabs = []
        for i in range(repeat):
            tabs.append(' \u200b')
        return ''.join(tabs)

    @staticmethod
    async def propagate_to_eh(bot, ctx, error):
        await ctx.message.add_reaction('<:blue_warn:703822784660373564>')
        reaction, user = await bot.wait_for(
            'reaction_add',
            check=lambda r, u: r.message.id == ctx.message.id
            and u.id in [ctx.author.id, 680835476034551925]
        )
        if str(reaction.emoji) == '<:blue_warn:703822784660373564>':
            return await ctx.send(error)

    class ExHandler:
        """
        Handles exceptions and returns True if there is no error
        or False if there is an error. A specific error type can be passed,
        defaults to Exception

        Usage:
            async with ctx.ExHandler(commands.MissingPermissions) as out:
                await bot.get_command('lock').can_run(ctx)
            if out.res:
                # do a thing
            else:
                # do the failure thing

        This manager can also be used to propagate directly to the bot's
        error handler. This is accomplished by passing a tuple of values
        to the constructor.

        Usage:
            async with ctx.ExHandler(propagate=(bot, ctx)) as out:
                await bot.get_command('lock').can_run(ctx)
        """

        def __init__(
                self, *, exception_type=None,
                propagate=(None, None), message: str = None):
            self.res = False
            self.ex_type = exception_type
            self.should_prop = False
            self.message = message
            if propagate and propagate[0] is not None and propagate[1] \
                    is not None:
                self.bot, self.ctx = propagate
                self.should_prop = True

        async def __aenter__(self):
            return self

        async def __aexit__(self, type, val, tb):
            if isinstance(val, self.ex_type or Exception):
                self.res = False
                if self.should_prop is True:
                    await Context.propagate_to_eh(
                        self.bot, self.ctx, self.message
                        or (val if str(type) != '' else type))
            else:
                self.res = True
            return True
