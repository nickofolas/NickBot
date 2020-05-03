import asyncio
import copy

import discord
from discord.ext.commands import Paginator as CommandPaginator
from discord.ext import menus

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


class CannotPaginate(Exception):
    pass


class Pages:
    """Implements a paginator that queries the user for the
    pagination interface.
    Pages are 1-index based, not 0-index based.
    If the user does not reply within 2 minutes then the pagination
    interface exits automatically.
    Parameters
    ------------
    ctx: Context
        The context of the command.
    entries: List[str]
        A list of entries to paginate.
    per_page: int
        How many entries show up per page.
    show_entry_count: bool
        Whether to show an entry count in the footer.
    Attributes
    -----------
    embed: discord.Embed
        The embed object that is being used to send pagination info.
        Feel free to modify this externally. Only the description,
        footer fields, and colour are internally modified.
    permissions: discord.Permissions
        Our permissions for the channel.
    """

    def __init__(self, ctx, *, entries, per_page=12, show_entry_count=True):
        self.bot = ctx.bot
        self.entries = entries
        self.message = ctx.message
        self.channel = ctx.channel
        self.author = ctx.author
        self.per_page = per_page
        pages, left_over = divmod(len(self.entries), self.per_page)
        if left_over:
            pages += 1
        self.maximum_pages = pages
        self.embed = discord.Embed(colour=discord.Color.main)
        self.paginating = len(entries) > per_page
        self.show_entry_count = show_entry_count
        self.reaction_emojis = [
            ('<:track_backward:703845740702859345>', self.first_page),
            ('<:arrow_back:703845714102583297>', self.previous_page),
            ('<:x_:703739402094117004>', self.stop_pages),
            ('<:arrow_fw:703845721874366568>', self.next_page),
            ('<:track_forward:703845753696813076>', self.last_page),
        ]

        if ctx.guild is not None:
            self.permissions = self.channel.permissions_for(ctx.guild.me)
        else:
            self.permissions = self.channel.permissions_for(ctx.bot.user)

        if not self.permissions.embed_links:
            raise CannotPaginate('Bot does not have embed links permission.')

        if not self.permissions.send_messages:
            raise CannotPaginate('Bot cannot send messages.')

        if self.paginating:
            # verify we can actually use the pagination session
            if not self.permissions.add_reactions:
                raise CannotPaginate('Bot does not have add reactions permission.')

            if not self.permissions.read_message_history:
                raise CannotPaginate('Bot does not have Read Message History permission.')

    def get_page(self, page):
        base = (page - 1) * self.per_page
        return self.entries[base:base + self.per_page]

    def get_content(self, entries, page, *, first=False):
        return None

    def get_embed(self, entries, page, *, first=False):
        self.prepare_embed(entries, page, first=first)
        return self.embed

    def prepare_embed(self, entries, page, *, first=False):
        p = []
        for index, entry in enumerate(entries, 1 + ((page - 1) * self.per_page)):
            p.append(f'{index}. {entry}')

        if self.maximum_pages > 1:
            if self.show_entry_count:
                text = f'Page {page}/{self.maximum_pages} ({len(self.entries)} entries)'
            else:
                text = f'Page {page}/{self.maximum_pages}'

            self.embed.set_footer(text=text)

        if self.paginating and first:
            p.append('')
            p.append('Confused? React with \N{INFORMATION SOURCE} for more info.')

        self.embed.description = '\n'.join(p)

    async def show_page(self, page, *, first=False):
        self.current_page = page
        entries = self.get_page(page)
        content = self.get_content(entries, page, first=first)
        embed = self.get_embed(entries, page, first=first)

        if not self.paginating:
            return await self.channel.send(content=content, embed=embed)

        if not first:
            await self.message.edit(content=content, embed=embed)
            return

        self.message = await self.channel.send(content=content, embed=embed)
        for (reaction, _) in self.reaction_emojis:
            if self.maximum_pages == 2 and reaction in ('\u23ed', '\u23ee'):
                # no |<< or >>| buttons if we only have two pages
                # we can't forbid it if someone ends up using it but remove
                # it from the default set
                continue

            await self.message.add_reaction(reaction)

    async def checked_show_page(self, page):
        if page != 0 and page <= self.maximum_pages:
            await self.show_page(page)

    async def first_page(self):
        """Goes to the first page"""
        await self.show_page(1)

    async def last_page(self):
        """Goes to the last page"""
        await self.show_page(self.maximum_pages)

    async def next_page(self):
        """Goes to the next page"""
        await self.checked_show_page(self.current_page + 1)

    async def previous_page(self):
        """Goes to the previous page"""
        await self.checked_show_page(self.current_page - 1)

    async def show_current_page(self):
        if self.paginating:
            await self.show_page(self.current_page)

    async def stop_pages(self):
        """stops the interactive pagination session"""
        await self.message.delete()
        self.paginating = False

    def react_check(self, payload):
        if payload.user_id != self.author.id:
            return False

        if payload.message_id != self.message.id:
            return False

        to_check = str(payload.emoji)
        for (emoji, func) in self.reaction_emojis:
            if to_check == emoji:
                self.match = func
                return True
        return False

    async def paginate(self):
        """Actually paginate the entries and run the interactive loop if necessary."""
        first_page = self.show_page(1, first=True)
        if not self.paginating:
            await first_page
        else:
            # allow us to react to reactions right away if we're paginating
            self.bot.loop.create_task(first_page)

        while self.paginating:
            try:
                loop = self.bot.loop
                # Ensure the name exists for the cancellation handling
                tasks = []
                while self.paginating:
                    tasks = [
                        asyncio.ensure_future(self.bot.wait_for('raw_reaction_add', check=self.react_check)),
                        asyncio.ensure_future(self.bot.wait_for('raw_reaction_remove', check=self.react_check))
                    ]
                    done, pending = await asyncio.wait(tasks, timeout=120.0, return_when=asyncio.FIRST_COMPLETED)
                    for task in pending:
                        task.cancel()

                    if len(done) == 0:
                        raise asyncio.TimeoutError()

                    # Exception will propagate if e.g. cancelled or timed out
                    payload = done.pop().result()
                    await self.match()
            except asyncio.TimeoutError:
                self.paginating = False
                try:
                    await self.message.delete()
                except:
                    pass
                finally:
                    break


"""ext.menus classes below"""


class CSMenu(menus.MenuPages):
    """Subclass of menus.MenuPages to customize emojis and behavior"""

    def __init__(self, source, **kwargs):
        super().__init__(source, **kwargs)
        for b in ['⏮️', '◀️', '⏹️', '▶️', '⏭️']:
            super().remove_button(b)

    def _skip_double_triangle_buttons(self):
        max_pages = self._source.get_max_pages()
        if max_pages is None:
            return True
        return max_pages <= 2

    async def _get_kwargs_from_page(self, page):
        value = await discord.utils.maybe_coroutine(self._source.format_page, self, page)
        if isinstance(value, dict):
            return value
        elif isinstance(value, str):
            return {'content': value, 'embed': None}
        elif isinstance(value, discord.Embed):
            return {'embed': value.set_footer(text=f'Page {self.current_page+1}/{self._source.get_max_pages()}'), 'content': None}

    @menus.button(
            '<:track_backward:703845740702859345>\ufe0f',
            position=menus.First(0), skip_if=_skip_double_triangle_buttons)
    async def go_to_first_page(self, payload):
        """go to the first page"""
        await self.show_page(0)

    @menus.button('<:arrow_back:703845714102583297>\ufe0f', position=menus.First(1))
    async def go_to_previous_page(self, payload):
        """go to the previous page"""
        await self.show_checked_page(self.current_page - 1)

    @menus.button('<:arrow_fw:703845721874366568>\ufe0f', position=menus.Last(0))
    async def go_to_next_page(self, payload):
        """go to the next page"""
        await self.show_checked_page(self.current_page + 1)

    @menus.button(
            '<:track_forward:703845753696813076>\ufe0f',
            position=menus.Last(1), skip_if=_skip_double_triangle_buttons)
    async def go_to_last_page(self, payload):
        """go to the last page"""
        # The call here is safe because it's guarded by skip_if
        await self.show_page(self._source.get_max_pages() - 1)

    @menus.button('<:x_:703739402094117004>\ufe0f', position=menus.First(1))
    async def stop_pages(self, payload):
        """stops the pagination session."""
        self.stop()


class GoogleMenu(menus.ListPageSource):
    def __init__(self, entr, per_page=1, image: bool = False):
        super().__init__(entr, per_page=per_page)
        self.image = image

    async def format_page(self, menu, page):
        embed = discord.Embed(
            title=page[0], description=page[1], url=page[2], color=discord.Color.main)
        if self.image:
            embed.set_image(url=page[3])
            embed.description = None
        return embed


class BareBonesMenu(menus.ListPageSource):
    def __init__(self, entr, per_page, *, embed: discord.Embed = None):
        super().__init__(entr, per_page=per_page)
        self.embed = embed

    async def format_page(self, menu, page):
        if self.embed:
            embed = copy.copy(self.embed)
            embed.description = '\n'.join(page)
            return embed
        else:
            return discord.Embed(description='\n'.join(page), color=discord.Color.main)


class ShellMenu(menus.ListPageSource):
    def __init__(self, *args, code_lang=None, **kwargs):
        self.code_lang = code_lang
        super().__init__(*args, **kwargs)

    async def format_page(self, menu, page):
        if isinstance(page, str):
            return page
        else:
            return f'```{self.code_lang or ""}\n' + ''.join(page) + '```'
