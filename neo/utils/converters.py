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
import itertools
import re
from asyncio import gather
from collections import namedtuple
from contextlib import suppress
from datetime import datetime, timedelta
from functools import partial

import discord
import yarl
from dateutil.relativedelta import relativedelta
from discord.ext import commands
from neo.models import GHRepo, GHUser, Redditor, Submission, Subreddit

__all__ = (
    "BoolConverter",
    "BetterUserConverter",
    "CBStripConverter",
    "RedditConverter",
    "ArbitraryRedditConverter",
    "GitHubConverter",
    "ArbitraryGitHubConverter",
    "TimeConverter",
)

RedditMatch = namedtuple("RedditMatch", "name id match")
TimeOutput = namedtuple("TimeOutput", "time string")
u_conv = commands.UserConverter()
m_conv = commands.MemberConverter()

reddit_url = re.compile(
    r"^((https://)?(www\.|old\.|new\.)?reddit.com)?/?"
    r"((?P<type>u|r)(ser)?/)?(?P<name>[\w\-]*)(/comme"
    r"nts/(?P<id>[\w\-\_]*))?/?",
    re.I,
)
github_pattern = re.compile(
    r"^((https://)?(www\.)?github.com)?/?(?P<user>[\w"
    r"\.\-]*)/?(?P<repo>[\w\-\.]*)?/?",
    re.I,
)
dt_re = re.compile(
    r"""((?P<years>[0-9])\s?(?:years?|y))?
                        ((?P<months>[0-9]{1,2})\s?(?:months?|mo))?
                        ((?P<weeks>[0-9]{1,4})\s?(?:weeks?|w))?
                        ((?P<days>[0-9]{1,5})\s?(?:days?|d))?
                        ((?P<hours>[0-9]{1,5})\s?(?:hours?|h))?
                        ((?P<minutes>[0-9]{1,5})\s?(?:minutes?|m))?
                        ((?P<seconds>[0-9]{1,5})\s?(?:seconds?|s))?""",
    re.X,
)
github_base = yarl.URL("https://api.github.com")
reddit_base = yarl.URL("https://www.reddit.com")


class BoolConverter(commands.Converter):
    async def convert(self, ctx, argument):
        true_values = ["on", "yes", "true", "y", "1"]
        false_values = ["off", "no", "false", "n", "0"]
        if argument.lower() in true_values:
            return True
        elif argument.lower() in false_values:
            return False
        else:
            raise commands.BadArgument(
                "Input could not be converted into a true or false result"
            )


class BetterUserConverter(commands.Converter):
    async def convert(self, ctx, argument):
        out = ctx.author if not argument else None
        for converter in (m_conv, u_conv):
            if out:
                break
            with suppress(Exception):
                out = await converter.convert(ctx, argument)
        if out is None:
            try:
                out = await ctx.bot.fetch_user(argument)
            except discord.HTTPException:
                raise commands.CommandError("Invalid user provided")
        return out


class CBStripConverter(commands.Converter):
    async def convert(self, ctx, argument) -> str:
        if argument.startswith("```") and argument.endswith("```"):
            return "\n".join(argument.split("\n")[1:-1])

            # remove `foo`
        return argument.strip("` \n")


class RedditConverter(commands.Converter):
    async def convert(self, ctx, argument):
        if match := re.match(reddit_url, argument.strip("<>")):
            return RedditMatch(
                match.groupdict().get("name"), match.groupdict().get("id"), match
            )
        raise commands.CommandError(f"Invalid argument '{argument}'")


class ArbitraryRedditConverter(commands.Converter):
    async def convert(self, ctx, argument):
        _redirects = True
        _key_depth = None
        groupdict = reddit_url.match(argument.strip("<>")).groupdict()
        check_list = [k for k, v in groupdict.items() if v]
        if len(check_list) == 1 and check_list[-1] == "name":
            raise commands.CommandError(
                "A Reddit entity could not be resolved from the input."
                " Make sure you use a valid model (`r/subreddit`, "
                "`u/user`, or a submission URL)"
            )
        if (_type := groupdict.get("type")) != "u":
            if (_id := groupdict.get("id")) is not None:
                url = reddit_base / "comments/{}/.json".format(_id)
                model = Submission
                _key_depth = (0, "data", "children", 0, "data")
            elif _type == "r":
                url = reddit_base / "r/{}/about.json".format(groupdict.get("name"))
                model = Subreddit
                _redirects = False
                _key_depth = ("data",)
            async with ctx.bot.session.get(url, allow_redirects=_redirects) as resp:
                if resp.status != 200:
                    raise commands.CommandError(
                        "Couldn't fetch entity [status code {}]".format(resp.status)
                    )
                json = await resp.json()
            _json = json
            for key in _key_depth:
                json = json.__getitem__(key)
            return model(json, original=_json)
        elif _type == "u":
            name = groupdict.get("name")
            about_url = reddit_base / "u/{}/about.json".format(name)
            troph_url = reddit_base / "u/{}/trophies.json".format(name)
            resps = await gather(*map(ctx.bot.session.get, (about_url, troph_url)))
            if any(r.status != 200 for r in resps):
                raise commands.CommandError(
                    "Couldn't fetch user [status codes {}]".format(
                        ", ".join(map(lambda r: str(r.status), resps))
                    )
                )
            about, trophies = await gather(*map(lambda resp: resp.json(), resps))
            return Redditor(about_data=about, trophy_data=trophies)


class GitHubConverter(commands.Converter):
    async def convert(self, ctx, argument):
        return github_pattern.search(argument.strip("<>")).groupdict()


class ArbitraryGitHubConverter(commands.Converter):
    async def convert(self, ctx, argument):
        groupdict = github_pattern.match(argument.strip("<>")).groupdict()
        if groupdict.get("repo"):
            url = github_base / "repos/{0}/{1}".format(*groupdict.values())
            model = GHRepo
        elif groupdict.get("user"):
            url = github_base / "users/{}".format(groupdict["user"])
            model = GHUser
        else:
            raise commands.CommandError(
                "A GitHub entity could not be resolved from the given argument"
            )
        async with ctx.bot.session.get(url) as resp:
            if resp.status != 200:
                raise commands.CommandError(
                    f"Couldn't find the given entity [Error code {resp.status}]"
                )
            json = await resp.json()
        return model(json)


class TimeConverter(commands.Converter):
    async def convert(self, ctx, argument):
        found = dict()
        for match in dt_re.finditer(argument):
            found.update(
                dict(filter(lambda i: i[1] is not None, match.groupdict().items()))
            )
        delta = relativedelta(**{k: int(v) for k, v in found.items()}) + timedelta(
            seconds=1
        )
        return TimeOutput(time=datetime.utcnow() + delta, string=argument)
