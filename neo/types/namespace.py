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

__all__ = ('Namespace', 'ImmutableNamespace', 'PrivateNamespace', 'NestedNamespace')

class Namespace:
    """Base namespace"""
    def __init__(self, **attrs):
        vars(self).update(attrs)

    def __repr__(self):
        return '<{0.__class__.__name__} {1}>'.format(
            self, ' '.join(f'{k}={v!r}' for k, v in vars(self).items()))

class ImmutableNamespace(Namespace):
    """An immutable namespace"""
    def __setattr__(self, key, value):
        raise TypeError(f'{self.__class__.__name__} is immutable.')

class PrivateNamespace(Namespace):
    """A namespace whose repr hides its attrs"""
    def __repr__(self):
        return f'<{self.__class__.__name__} attr_count={len(vars(self))}>'

class NestedNamespace(Namespace):
    """A namespace that recursively sets its attributes"""
    def __init__(self, **attrs):
        for k, v in filter(lambda i: isinstance(i[1], dict),attrs.items()):
            attrs[k] = self.__class__(**v)
        super().__init__(**attrs)      

# Below here are more novelty classes than anything

class ImmutablePrivateNestedNamespace(ImmutableNamespace, PrivateNamespace, NestedNamespace):
    """An immutable nested namespace whose repr hides its attrs"""

class ImmutablePrivateNamespace(ImmutableNamespace, PrivateNamespace):
    """An immutable namespace whose repr hides its attrs"""

class ImmutableNestedNamespace(ImmutableNamespace, NestedNamespace):
    """An immutable nested namespace"""

class PrivateNestedNamespace(PrivateNamespace, NestedNamespace):
    """A nested namespace whose repr hides its attrs"""

