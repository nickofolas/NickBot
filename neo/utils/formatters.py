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
import ast
import io
import re
import textwrap
import traceback
from datetime import datetime, timedelta

import import_expression

__all__ = (
    "group",
    "flatten",
    "prettify_text",
    "pluralize",
    "clean_bytes",
    "from_tz",
    "bar_make",
)


def group(iterable, page_len=50):
    pages = []
    while iterable:
        pages.append(iterable[:page_len])
        iterable = iterable[page_len:]
    return pages


def flatten(iterable, *, lazy=True):
    def inner():
        for item in iterable:
            if hasattr(item, "__iter__") and not isinstance(item, str):
                yield from flatten(item)
            else:
                yield item

    flattened = inner()
    return flattened if lazy else [*flattened]


def pluralize(inp, value):
    if isinstance(value, list):
        inp = inp + "s" if len(value) != 1 else inp
    if isinstance(value, int):
        inp = inp + "s" if value != 1 else inp
    return inp


def prettify_text(content):
    return content.replace("_", " ").capitalize()


def from_tz(str_time):
    if str_time is None:
        return None
    return datetime.strptime(str_time, "%Y-%m-%dT%H:%M:%SZ")


def clean_bytes(line):
    text = line.decode("utf-8").replace("\r", "").strip("\n")
    return re.sub(r"\x1b[^m]*m", "", text).replace("``", "`\u200b`").strip("\n")


def bar_make(value, gap, *, length=10, point=False, fill="█", empty=" "):
    bar = ""
    scaled_value = (value / gap) * length
    for i in range(1, (length + 1)):
        check = (i == round(scaled_value)) if point else (i <= scaled_value)
        bar += fill if check else empty
    if point and (bar.count(fill) == 0):
        bar = fill + bar[1:]
    return bar
