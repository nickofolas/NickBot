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
import re
import io
import os
import zlib

import discord
from discord.ext import commands

# TODO: rtfs to search dpy source


def finder(text, collection, *, key=None, lazy=True):
    suggestions = []
    text = str(text)
    pat = '.*?'.join(map(re.escape, text))
    regex = re.compile(pat, flags=re.IGNORECASE)
    for item in collection:
        to_search = key(item) if key else item
        r = regex.search(to_search)
        if r:
            suggestions.append((len(r.group()), r.start(), item))

    def sort_key(tup):
        if key:
            return tup[0], tup[1], key(tup[2])
        return tup

    if lazy:
        return (z for _, _, z in sorted(suggestions, key=sort_key))
    else:
        return [z for _, _, z in sorted(suggestions, key=sort_key)]


class SphinxObjectFileReader:
    # Inspired by Sphinx's InventoryFileReader
    BUFSIZE = 16 * 1024

    def __init__(self, buffer):
        self.stream = io.BytesIO(buffer)

    def readline(self):
        return self.stream.readline().decode('utf-8')

    def skipline(self):
        self.stream.readline()

    def read_compressed_chunks(self):
        decompressor = zlib.decompressobj()
        while True:
            chunk = self.stream.read(self.BUFSIZE)
            if len(chunk) == 0:
                break
            yield decompressor.decompress(chunk)
        yield decompressor.flush()

    def read_compressed_lines(self):
        buf = b''
        for chunk in self.read_compressed_chunks():
            buf += chunk
            pos = buf.find(b'\n')
            while pos != -1:
                yield buf[:pos].decode('utf-8')
                buf = buf[pos + 1:]
                pos = buf.find(b'\n')


class Docs(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._rtfm_cache = dict()
        self.bot.loop.create_task(self.rtfm_lookup_table_append(
                'dpy', 'https://discordpy.readthedocs.io/en/latest'))
        self.bot.loop.create_task(self.rtfm_lookup_table_append(
            'python', 'https://docs.python.org/3'))

    def parse_object_inv(self, stream, url):
        # key: URL
        # n.b.: key doesn't have `discord` or `discord.ext.commands` namespaces
        result = {}

        # first line is version info
        inv_version = stream.readline().rstrip()

        if inv_version != '# Sphinx inventory version 2':
            raise RuntimeError('Invalid objects.inv file version.')

        # next line is "# Project: <name>"
        # then after that is "# Version: <version>"
        projname = stream.readline().rstrip()[11:]
        version = stream.readline().rstrip()[11:]

        # next line says if it's a zlib header
        line = stream.readline()
        if 'zlib' not in line:
            raise RuntimeError('Invalid objects.inv file, not z-lib compatible.')

        # This code mostly comes from the Sphinx repository.
        entry_regex = re.compile(r'(?x)(.+?)\s+(\S*:\S*)\s+(-?\d+)\s+(\S+)\s+(.*)')
        for line in stream.read_compressed_lines():
            match = entry_regex.match(line.rstrip())
            if not match:
                continue

            name, directive, prio, location, dispname = match.groups()
            domain, _, subdirective = directive.partition(':')
            if directive == 'py:module' and name in result:
                # From the Sphinx Repository:
                # due to a bug in 1.1 and below,
                # two inventory entries are created
                # for Python modules, and the first
                # one is correct
                continue

            # Most documentation pages have a label
            if directive == 'std:doc':
                subdirective = 'label'

            if location.endswith('$'):
                location = location[:-1] + name

            key = name if dispname == '-' else dispname
            prefix = f'{subdirective}:' if domain == 'std' else ''

            if projname == 'discord.py':
                key = key.replace('discord.ext.commands.', '').replace('discord.', '')

            result[f'{prefix}{key}'] = os.path.join(url, location)

        return result

    async def rtfm_lookup_table_append(self, key, page):
        async with self.bot.session.get(page + '/objects.inv') as resp:
            if resp.status != 200:
                raise RuntimeError('Cannot build rtfm lookup table, try again later.')

            stream = SphinxObjectFileReader(await resp.read())
            self._rtfm_cache[key] = self.parse_object_inv(stream, page)

    async def do_rtfm(self, ctx, key, obj):
        page_types = {
            'dpy': 'https://discordpy.readthedocs.io/en/latest',
            'python': 'https://docs.python.org/3',
        }

        if key not in page_types.keys():
            page_types[key] = f'https://{key}.readthedocs.io/en/latest'

        if not hasattr(self, '_rtfm_cache'):
            await ctx.trigger_typing()
            self._rtfm_cache = dict()
            await self.rtfm_lookup_table_append('dpy', 'https://discordpy.readthedocs.io/en/latest')
            await self.rtfm_lookup_table_append('python', 'https://docs.python.org/3')

        try:
            cache = list(self._rtfm_cache[key].items())
            if obj is None:
                return await ctx.safe_send(page_types[key])
        except KeyError:
            await ctx.trigger_typing()
            await self.rtfm_lookup_table_append(key, f'https://{key}.readthedocs.io/en/latest')
            cache = list(self._rtfm_cache[key].items())
            if obj is None:
                return await ctx.safe_send(page_types[key])

        obj = re.sub(r'^(?:discord\.(?:ext\.)?)?(?:commands\.)?(.+)', r'\1', obj)

        if key.startswith('dpy'):
            # point the abc.Messageable types properly:
            q = obj.lower()
            for name in dir(discord.abc.Messageable):
                if name[0] == '_':
                    continue
                if q == name:
                    obj = f'abc.Messageable.{name}'
                    break

        def transform(tup):
            return tup[0]

        matches = finder(obj, cache, key=lambda t: t[0], lazy=False)[:8]

        e = discord.Embed(colour=discord.Color.main)
        if len(matches) == 0:
            return await ctx.send(
                embed=discord.Embed(
                    title='',
                    description='No results :(',
                    color=discord.Color.main))

        e.description = '\n'.join(f'[`{key}`]({url})' for key, url in matches)
        await ctx.send(embed=e)

    @commands.group(aliases=['rtfd'], invoke_without_command=True, hidden=True)
    async def rtfm(self, ctx, doc_name, *, obj=None):
        """
        Do RTFM for any readthedocs documentation
        Documentation MUST be available on rtd!
        """
        await self.do_rtfm(ctx, doc_name, obj)

    @rtfm.command(name='python', aliases=['py'], hidden=True)
    async def rtfm_python(self, ctx, *, obj=None):
        """Gives you a documentation link for a Python entity."""
        await self.do_rtfm(ctx, 'python', obj)

    @rtfm.command(name='dpy', aliases=['discord.py', 'discord'])
    async def rtfm_dpy(self, ctx, *, obj=None):
        """Gives you a documentation link for a discord.py entity"""
        await self.do_rtfm(ctx, 'dpy', obj)

    @rtfm.command(name='dump')
    @commands.is_owner()
    async def rtfm_drop_cache(self, ctx):
        """Dump all currently cached documentations"""
        if not self._rtfm_cache.items():
            raise commands.CommandError('Cache is already empty')
        y_n = await ctx.prompt('Are you sure you want to dump the RTFM cache?')
        if y_n is True:
            self._rtfm_cache.clear()

    @rtfm.command(name='cache')
    @commands.is_owner()
    async def view_rtfm_cache(self, ctx):
        """View all currently cached documentations for rtfm"""
        cached_docs = '\n'.join([k for k in self._rtfm_cache.keys()]) \
            or 'No cached docs'
        await ctx.safe_send(
            embed=discord.Embed(
                description=cached_docs,
                color=discord.Color.main))


def setup(bot):
    bot.add_cog(Docs(bot))
