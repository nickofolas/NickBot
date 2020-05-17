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


class Flags:
    def __init__(self, value):
        self.value = value
        self.flags = [*self.__iter__()]

    def __iter__(self):
        for k, v in self.__class__.__dict__.items():
            if not isinstance(v, property):
                continue
            if self.has_flag(getattr(self, k)):
                yield k

    def __repr__(self):
        return f"<{self.__class__.__name__} value={self.value} flags={self.flags}>"

    def has_flag(self, v):
        return (self.value & v) == v

    @property
    def discord_employee(self):
        return 1 << 0

    @property
    def discord_partner(self):
        return 1 << 1

    @property
    def hs_events(self):
        return 1 << 2

    @property
    def bug_hunter_lvl1(self):
        return 1 << 3

    @property
    def mfa_sms(self):
        return 1 << 4

    @property
    def premium_promo_dismissed(self):
        return 1 << 5

    @property
    def hs_bravery(self):
        return 1 << 6

    @property
    def hs_brilliance(self):
        return 1 << 7

    @property
    def hs_balance(self):
        return 1 << 8

    @property
    def early_supporter(self):
        return 1 << 9

    @property
    def team_user(self):
        return 1 << 10

    @property
    def system(self):
        return 1 << 12

    @property
    def unread_sys_msg(self):
        return 1 << 13

    @property
    def bug_hunter_lvl2(self):
        return 1 << 14

    @property
    def underage_deleted(self):
        return 1 << 15

    @property
    def verified_bot(self):
        return 1 << 16

    @property
    def verified_dev(self):
        return 1 << 17
