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
import yaml

from ..types.namespace import ImmutablePrivateNamespace

__all__ = ('conf', 'secrets')

def load_public_config():
    with open('neo/core/config.public.yml', 'r') as config:
        return yaml.safe_load(config)

def load_private_config():
    with open('neo/core/config.private.yml', 'r') as config:
        load = yaml.safe_load(config)
    return ImmutablePrivateNamespace(**load)

conf = load_public_config()
secrets = load_private_config()

