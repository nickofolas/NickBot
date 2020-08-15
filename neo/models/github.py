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
from string import ascii_letters
from random import choice

from yarl import URL

from neo.utils.formatters import from_tz

__all__ = ('GHUser', 'GHRepo')

class GHUser:
    __slots__ = ('data', 'name', 'url', 'bio', 'av_url',
                 'location', 'user_id', 'created', 'updated',
                 'refol')

    def __init__(self, data):
        self.data = data
        self.name = data.get('login')
        self.url = URL(data.get('html_url'))
        self.bio = data.get('bio')
        self.av_url = URL(data.get('avatar_url'))\
            .update_query(f'{choice(ascii_letters)}={choice(ascii_letters)}')
        # ^ This looks unnecessary, but it helps bypass discord's caching the avatar images
        self.location = data.get('location')
        self.user_id = data.get('id')
        self.created = from_tz(data.get('created_at'))
        self.updated = from_tz((data.get('updated_at')))
        self.refol = {k: v for k, v in self.data.items() if k in 
                      ('public_repos', 'public_gists', 'followers', 'following')}


class GHRepo:
    __slots__ = ('data', 'name', 'full_name', 'repo_id', 'owner', 'url', 'description', 'created',
                 'last_push', 'gazers', 'license_id', 'forks', 'language', 'watchers', 'html_url')

    def __init__(self, data):
        self.data = data
        self.name = data.get('name')
        self.full_name = data.get('full_name')
        self.repo_id = data.get('id')
        self.owner = GHUser(data.get('owner'))
        self.html_url = URL(data.get('html_url'))
        self.url = URL(data.get('url'))
        self.description = data.get('description')
        self.created = from_tz(data.get('created_at'))
        self.last_push = from_tz(data.get('pushed_at'))
        self.gazers = data.get('stargazers_count')
        self.license_id = self.license()
        self.forks = data.get('forks')
        self.language = data.get('language')
        self.watchers = data.get('subscribers_count')

    def license(self):
        if lic := self.data.get('license'):
            return lic.get('spdx_id')
        return None

    async def commit_count(self, session):
        async with session.get(self.url / 'commits', params={'per_page': 1}) as resp:
            _commit_count = len(await resp.json())
        last_page = resp.links.get('last')
        if last_page:
            _commit_count = int(URL(last_page['url']).query['page'])
        return f"{_commit_count:,}"

