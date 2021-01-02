"""
neo Discord bot
Copyright (C) 2021 nickofolas

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

__all__ = ("conf", "secrets")


def load_config():
    with open("neo/core/config.yml", "r", encoding="utf-8") as config:
        raw = yaml.safe_load(config)
    secrets = raw["secret"]
    assets = raw["assets"]
    return assets, ImmutablePrivateNamespace(**secrets)


conf, secrets = load_config()
