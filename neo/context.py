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
import contextlib
import re
from contextlib import suppress
import asyncio

from discord.ext import commands
import discord

import neo
import neo.utils.paginator as pages


class Codeblock:
    def __init__(self, *, content, lang=None, cb_safe=True):
        self.lang = lang or ''
        self.cb_safe = cb_safe
        self.content = content.replace('``', '`\N{ZWSP}`') if cb_safe else content

    def __str__(self):
        return f"```{self.lang}\n{self.content}\n```"

    def __repr__(self):
        return f"<Codeblock content={self.content!r} lang={self.lang!r} cb_safe={self.cb_safe}>"


class Context(commands.Context):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    async def prompt(self, message):
        emojis = {
            neo.conf['emojis']['check_button']: True,
            neo.conf['emojis']['x_button']: False}
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
            if match := re.search(re.compile(r'([a-zA-Z0-9]{24}\.[a-zA-Z0-9]{6}\.[a-zA-Z0-9_\-]{27}|mfa\.['
                                             r'a-zA-Z0-9_\-]{84})'), content):
                content = content.replace(match.group(0), '[token omitted]')
            if len(content) > 2000:
                async with self.bot.session.post(
                        "https://mystb.in/documents",
                        data=content.encode('utf-8')) as post:
                    post = await post.json()
                    url = f"https://mystb.in/{post['key']}"
                    await self.send(f'Output: <{url}>')
            else:
                return await self.send(content, **kwargs)
        else:
            await self.send(**kwargs)

    @staticmethod
    def tick(opt, label=None):
        lookup = {
            True: neo.conf['emojis']['check_button'],
            False: neo.conf['emojis']['x_button'],
            None: neo.conf['emojis']['neutral_button'],
        }
        emoji = lookup.get(opt, neo.conf['emojis']['x_button'])
        if label is not None:
            return f'{emoji}: {label}'
        return emoji

    @staticmethod
    def toggle(opt):
        options = {
            True: neo.conf['emojis']['toggleon'],
            False: neo.conf['emojis']['toggleoff'],
            None: neo.conf['emojis']['toggleoff']
        }
        emoji = options.get(opt, neo.conf['emojis']['toggleoff'])
        return emoji

    @staticmethod
    def codeblock(**kwargs):
        return Codeblock(**kwargs)

    @staticmethod
    def tab(repeat=1):
        return ' \u200b' * repeat

    async def quick_menu(self, entries, per_page, *, template: discord.Embed = None, **kwargs):
        source = pages.BareBonesMenu(entries, per_page=per_page, embed=template)
        menu = pages.CSMenu(source, **kwargs)
        await menu.start(self)

    @contextlib.asynccontextmanager
    async def loading(self, *, prop=True, tick=True, exc_ignore=None):
        clear_reacts = self.message.remove_reaction(neo.conf['emojis']['loading'], self.me)
        tasks = [clear_reacts]
        try:
            yield await self.message.add_reaction(neo.conf['emojis']['loading'])
        except Exception as e:
            if exc_ignore and isinstance(e, exc_ignore):
                pass
            elif isinstance(e, (discord.Forbidden, discord.HTTPException)):
                yield False
                return
            else:
                if prop:
                    self.bot.dispatch('command_error', self, e)
        else:
            tasks.append(self.message.add_reaction(self.tick(True))) if tick else None
        finally:
            with suppress(discord.NotFound):
                await asyncio.gather(*tasks)

    async def propagate_error(self, error, do_emojis=True):
        if do_emojis is False:
            return await self.send(error)
        with suppress(Exception):
            await self.message.add_reaction(neo.conf['emojis']['warning_button'])
            try:
                reaction, user = await self.bot.wait_for(
                    'reaction_add',
                    check=lambda r, u: r.message.id == self.message.id
                    and u.id in [self.author.id, *self.bot.owner_ids], timeout=30.0
                )
            except asyncio.TimeoutError:
                await self.message.remove_reaction(
                    neo.conf['emojis']['warning_button'], self.me)
                return
            if str(reaction.emoji) == neo.conf['emojis']['warning_button']:
                return await self.send(error)

