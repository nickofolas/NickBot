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
from contextlib import suppress
from collections import namedtuple

PendingValue = namedtuple('PendingValue', 'item task')

class TimedSet(set):
    def __init__(self, *args, decay_time, loop = None, **kwargs):
        self.decay_time = decay_time
        self.loop = loop or asyncio.get_event_loop()
        self.running = {}
        super().__init__(*args, **kwargs)

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

class Cache(dict):
    def __init__(self, *, db_query, loop = None, query_params = [], pool, key, lazy_load = False):
        self.pool = pool
        self.loop = loop or asyncio.get_running_loop()
        self.db_query = db_query
        self.query_params = query_params
        self.key = key
        if not lazy_load:
            loop.create_task(self._build_cache())

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
