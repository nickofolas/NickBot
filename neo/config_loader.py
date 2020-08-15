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
from types import SimpleNamespace

import yaml

class PrivateNamespace(SimpleNamespace):
    """
    SimpleNamespace that hides its attrs in the repr
    """
    def __repr__(self):
        return f'<{self.__class__.__name__} attr_count={len(vars(self))}>'

def load_public_config():
    with open('neo/config.public.yml', 'r') as config:
        return yaml.safe_load(config)

def load_private_config():
    with open('neo/config.private.yml', 'r') as config:
        load = yaml.safe_load(config)
    return PrivateNamespace(**load)

conf = load_public_config()
secrets = load_private_config()

