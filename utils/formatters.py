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
import io
from datetime import datetime, timedelta
import re

import matplotlib.pyplot as plt

from utils.config import conf


LANGUAGES = conf['hl_langs']


def group(iterable, page_len=50):
    pages = []
    while iterable:
        pages.append(iterable[:page_len])
        iterable = iterable[page_len:]
    return pages

def flatten(iterable):
    for item in iterable:
        if hasattr(item, '__iter__'):
            yield from flatten(item)
        else:
            yield item


def return_lang_hl(input_string) -> str:
    for possible_suffix in LANGUAGES:
        if input_string.endswith(possible_suffix):
            return possible_suffix
    return 'sh'


def pluralize(inp, value):
    if isinstance(value, list):
        inp = inp + 's' if len(value) != 1 else inp
    if isinstance(value, int):
        inp = inp + 's' if value != 1 else inp
    return inp


def prettify_text(content):
    return content.replace('_', ' ').capitalize()


def gen(guild, status_type):
    return len([m for m in guild.members if str(m.status) == status_type])


def from_tz(str_time):
    if str_time is None:
        return None
    return datetime.strptime(str_time, "%Y-%m-%dT%H:%M:%SZ")

class DTParser:
  def __init__(self):
    self.hdr = re.compile('(?P<time>[0-9]+)\\s?(?P<unit>s(econd)?|month|m(inute)?|h(our)?|d(ay)?|w(eek)?|y(ear)?)', re.IGNORECASE)
    self.mapping = {'s': 1, 'second': 1, 'm': 60, 'minute': 60, 'h': 3600, 'hour': 3600, 'd': 86400, 'day': 86400, 'month': 2592000, 'y': 3.154e+7, 'year': 3.154e+7}
  def __call__(self, to_parse):
    total = []
    for match in self.hdr.finditer(to_parse):
      ass = match.groupdict()
      total.append(int(ass['time']) * self.mapping[ass['unit']])
    return datetime.utcnow() + timedelta(seconds=sum(total) if total else 300)


class StatusChart:
    __slots__ = ('guild', 'labels', 'sizes', 'colors')

    # Pie chart, where the slices will be ordered and plotted counter-clockwise:
    def __init__(self, guild, labels: list, sizes: list, colors: list):
        self.guild = guild
        self.labels = labels
        self.sizes = sizes
        self.colors = colors

    def make_pie(self):
        fig1, ax1 = plt.subplots(figsize=(5, 5))
        ax1.pie(self.sizes, autopct='%1.1f%%', colors=self.colors, startangle=90)
        ax1.axis('equal')  # Equal aspect ratio ensures that pie is drawn as a circle.
        title_obj = plt.title(f'Statuses for {self.guild}')
        plt.setp(title_obj, color='w')
        plt.legend(self.labels, loc="upper right")
        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format='png', transparent=True)
        buf.seek(0)
        data = buf.read()
        return data


def bar_make(
        value: int, gap: int, *,
        fill: str = '█', empty: str = ' ',
        point: bool = False, length: int = 10):
    bar = ''

    percentage = (value/gap) * length

    if point:
        for i in range(0, length + 1):
            if i == round(percentage):
                bar += fill
            else:
                bar += empty
        return bar

    for i in range(1, length + 1):
        if i <= percentage:
            bar += fill
        else:
            bar += empty
    return bar
