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
from collections import namedtuple, defaultdict
from contextlib import suppress

__all__ = ("TimedSet", "DbCache")

PendingValue = namedtuple("PendingValue", "item task")


class TimedSet(set):
    def __init__(self, *args, decay_time, loop=None, **kwargs):
        self.decay_time = decay_time
        self.loop = loop or asyncio.get_event_loop()
        self.running = {}
        super().__init__(*args, **kwargs)
        for item in self:
            self.add(item)

    def add(self, item):
        with suppress(KeyError):
            if con := self.running.pop(item):
                con.task.cancel()
                self.discard(item)
        super().add(item)
        task = self.loop.create_task(self.decay(item))
        self.running[item] = PendingValue(item, task)

    async def decay(self, item):
        await asyncio.sleep(self.decay_time)
        self.discard(item)


class DbCache(defaultdict):
    def __init__(self, *, db_query, query_params=[], pool, key):
        super().__init__(dict)
        self.pool = pool
        self.db_query = db_query
        self.query_params = query_params
        self.key = key

    def __await__(self):
        return self._build_cache().__await__()

    async def _build_cache(self):
        data = await self.pool.fetch(self.db_query, *self.query_params)
        for record in data:
            copied = dict(record)
            self[copied.pop(self.key)] = copied
        return self

    async def refresh(self):
        self.clear()
        await self._build_cache()
        return self
