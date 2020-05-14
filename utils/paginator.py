import asyncio
import copy
from datetime import datetime

import discord
import humanize
from discord.ext import menus

from utils.config import conf

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
            return {'embed': value.set_footer(text=f'Page {self.current_page + 1}/{self._source.get_max_pages()}'),
                    'content': None}

    @menus.button(
        f'{conf["emoji_suite"]["menu_dleft"]}\ufe0f',
        position=menus.First(0), skip_if=_skip_double_triangle_buttons)
    async def go_to_first_page(self, payload):
        """go to the first page"""
        await self.show_page(0)

    @menus.button(f'{conf["emoji_suite"]["menu_left"]}\ufe0f', position=menus.First(1))
    async def go_to_previous_page(self, payload):
        """go to the previous page"""
        await self.show_checked_page(self.current_page - 1)

    @menus.button(f'{conf["emoji_suite"]["menu_right"]}\ufe0f', position=menus.Last(0))
    async def go_to_next_page(self, payload):
        """go to the next page"""
        await self.show_checked_page(self.current_page + 1)

    @menus.button(
        f'{conf["emoji_suite"]["menu_dright"]}\ufe0f',
        position=menus.Last(1), skip_if=_skip_double_triangle_buttons)
    async def go_to_last_page(self, payload):
        """go to the last page"""
        # The call here is safe because it's guarded by skip_if
        await self.show_page(self._source.get_max_pages() - 1)

    @menus.button(conf['emoji_suite']['search'], position=menus.First(2))
    async def go_to_inputted_page(self, payload):
        prompt = await self.ctx.send('Enter the number of the page you would like to go to')
        try:
            msg = await self.bot.wait_for('message', check=lambda m: m.author.id == self._author_id, timeout=10.0)
            ind = int(msg.content)
            await self.show_checked_page(ind - 1)
        except asyncio.TimeoutError:
            pass
        finally:
            await prompt.delete()

    @menus.button(f'{conf["emoji_suite"]["x_button"]}\ufe0f', position=menus.First(1))
    async def stop_pages(self, payload):
        """stops the pagination session."""
        self.stop()


class GoogleMenu(menus.ListPageSource):
    def __init__(self, entr, *, per_page=1, image: bool = False):
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
        if isinstance(page, str):
            if self.embed:
                embed = copy.copy(self.embed)
                embed.description = ''.join(page)
                return embed
            else:
                return discord.Embed(description=''.join(page), color=discord.Color.main)
        else:
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


class SnipeMenu(menus.ListPageSource):
    def __init__(self, entries, per_page=1):
        super().__init__(entries, per_page=per_page)

    async def format_page(self, menu, page):
        embed = discord.Embed(color=discord.Color.main)
        if page[1].attachments:
            embed.set_image(url=page[1].attachments[0].proxy_url)
        if page[1].embeds:
            embed = copy.copy(page[1].embeds[0])
        embed.set_author(
            name=f'{page[1].author.display_name} - {humanize.naturaltime(datetime.utcnow() - page[2])}',
            icon_url=page[1].author.avatar_url_as(static_format='png'))
        embed.description = ''.join(page[0])
        return embed
