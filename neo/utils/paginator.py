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
import asyncio
import contextlib
from datetime import datetime
from typing import List

import discord
import humanize
from discord.ext import menus

import neo

__all__ = ['CSMenu', 'BareBonesMenu', 'PagedEmbedMenu']


class CSMenu(menus.MenuPages, inherit_buttons=False):
    """Subclass of menus.MenuPages to customise emojis and behaviour"""

    def __init__(self, source, *, delete_on_button = False, footer_extra: str = None, **kwargs):
        self.delete_on_button = delete_on_button
        self.closed_via_button = False
        self.footer_extra = footer_extra
        super().__init__(source, **kwargs)

    def should_add_reactions(self):
        return True

    def _skip_double_triangle_buttons(self):
        max_pages = self._source.get_max_pages()
        if max_pages is None:
            return True
        return max_pages <= 2

    def _skip_single_arrows(self):
        max_pages = self._source.get_max_pages()
        if max_pages is None:
            return True
        return max_pages <= 1

    def reaction_check(self, payload):
        """Just extends the default reaction_check to use owner_ids"""
        if payload.message_id != self.message.id:
            return False
        if payload.user_id not in (*self.bot.owner_ids, self.bot.owner_id, self._author_id):
            return False
        return payload.emoji in self.buttons

    async def _get_kwargs_from_page(self, page):
        value = await discord.utils.maybe_coroutine(self._source.format_page, self, page)
        if isinstance(value, dict):
            return value
        elif isinstance(value, str):
            return {'content': f'{value}\nPage {self.current_page + 1}/{self._source.get_max_pages()}', 'embed': None}
        elif isinstance(value, discord.Embed):
            text = f'Page {self.current_page + 1}/{self._source.get_max_pages()}' if \
                self._source.get_max_pages() > 1 else ''
            if self.footer_extra:
                if not text:
                    text = self.footer_extra
                else:
                    text += f' | {self.footer_extra}'
            return {'embed': value.set_footer(
                text=text),
                    'content': None}

    async def finalize(self):
        if self.closed_via_button is True and self.delete_on_button is True:
            await self.message.delete()

    @menus.button(
        neo.conf['emojis']['menus']['menu_dleft'],
        position=menus.First(0), skip_if=_skip_double_triangle_buttons)
    async def go_to_first_page(self, payload):
        """go to the first page"""
        await self.show_page(0)

    @menus.button(neo.conf['emojis']['menus']['menu_left'], position=menus.First(1), skip_if=_skip_single_arrows)
    async def go_to_previous_page(self, payload):
        """go to the previous page"""
        await self.show_checked_page(self.current_page - 1)

    @menus.button(neo.conf['emojis']['menus']['menu_right'], position=menus.Last(), skip_if=_skip_single_arrows)
    async def go_to_next_page(self, payload):
        """go to the next page"""
        await self.show_checked_page(self.current_page + 1)

    @menus.button(
        neo.conf['emojis']['menus']['menu_dright'],
        position=menus.Last(1), skip_if=_skip_double_triangle_buttons)
    async def go_to_last_page(self, payload):
        """go to the last page"""
        await self.show_page(self._source.get_max_pages() - 1)

    @menus.button(neo.conf['emojis']['menus']['search'], position=menus.First(2), skip_if=_skip_double_triangle_buttons)
    async def number_page(self, payload):
        prompt = await self.ctx.send('Enter the number of the page you would like to go to')
        try:
            msg = await self.bot.wait_for('message', check=lambda m: m.author.id == self._author_id, timeout=10.0)
            ind = int(msg.content)
            await self.show_checked_page(ind - 1)
            with contextlib.suppress(Exception):
                await prompt.delete()
                await msg.delete()
        except asyncio.TimeoutError:
            pass

    @menus.button(neo.conf['emojis']['x_button'], position=menus.First(1))
    async def stop_pages(self, payload):
        """stops the pagination session."""
        self.closed_via_button = True
        self.stop()


class PagedEmbedMenu(menus.ListPageSource):
    def __init__(self, embeds: List[discord.Embed]):
        self.embeds = embeds
        super().__init__([*range(len(embeds))], per_page=1)

    async def format_page(self, menu, page):
        return self.embeds[page]


class BareBonesMenu(menus.ListPageSource):
    def __init__(self, entr, per_page, *, embed: discord.Embed = None):
        super().__init__(entr, per_page=per_page)
        self.embed = embed

    async def format_page(self, menu, page):
        join_str = '' if isinstance(page, str) else '\n'
        if self.embed:
            embed = self.embed.copy()
            embed.description = join_str.join(page)
            return embed
        else:
            return neo.Embed(description=join_str.join(page))

