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
import textwrap
from collections import namedtuple
from datetime import datetime

__all__ = ("Poll", "Submission", "SubListing", "Subreddit", "Redditor")

PollChoice = namedtuple("PollChoice", ["text", "votes"])


class Poll:
    def __init__(self, poll_data):
        self.data = poll_data
        self.deadline = datetime.fromtimestamp(
            poll_data.get("voting_end_timestamp") / 1000
        )
        self.total_votes = poll_data.get("total_vote_count")

    def __iter__(self):
        for option in self.data["options"]:
            yield PollChoice(text=option["text"], votes=option.get("vote_count", ""))


class Submission:
    __slots__ = (
        "data",
        "title",
        "nsfw",
        "text",
        "upvotes",
        "comments",
        "full_url",
        "img_url",
        "author",
        "author_url",
        "thumbnail",
        "poll",
        "created",
        "creation_delta",
        "original_json",
    )
    """Wraps up a Submission"""

    def __init__(self, data, *, original):
        self.original_json = original
        self.data = data
        self.title = textwrap.shorten(data.get("title"), width=252)
        self.nsfw = data.get("over_18")
        self.text = (
            textwrap.shorten(data.get("selftext"), width=1500)
            if data.get("selftext")
            else ""
        )
        self.upvotes = data.get("ups")
        self.comments = data.get("num_comments")
        self.full_url = "https://www.reddit.com" + data.get("permalink")
        self.img_url = data.get("url")
        self.thumbnail = data.get("thumbnail")
        self.author = data.get("author")
        self.author_url = f"https://www.reddit.com/user/{self.author}"
        self.created = data.get("created_utc")
        self.creation_delta = datetime.utcnow() - datetime.utcfromtimestamp(
            self.created
        )
        if p := data.get("poll_data"):
            self.poll = Poll(p)
        else:
            self.poll = None

    @property
    def is_gif(self):
        if p := self.data.get("preview"):
            if p2 := p.get("reddit_video_preview"):
                return p2.get("is_gif")
        return False


class SubListing:
    __slots__ = ("data", "allow_nsfw")
    """Generates a listing of posts from a Subreddit"""

    def __init__(self, data, *, allow_nsfw=False):
        self.data = data
        self.allow_nsfw = allow_nsfw

    def do_predicates(self, submission):
        predicates = [submission.is_gif is False]
        if not self.allow_nsfw:
            predicates.append(submission.nsfw is False)
        return all(predicates)

    @property
    def posts(self):
        for post in self.data["data"]["children"]:
            submission = Submission(post["data"], original=None)
            if not self.do_predicates(submission):
                continue
            yield submission


class Subreddit:
    __slots__ = (
        "data",
        "title",
        "icon_img",
        "prefixed",
        "subscribers",
        "pub_desc",
        "full_url",
        "created",
        "nsfw",
        "original_json",
    )
    """Wraps up a Subreddit's JSON"""

    def __init__(self, data, *, original=None):
        self.original_json = original
        self.data = data or {}
        self.title = data.get("title")
        self.icon_img = data.get("icon_img")
        self.prefixed = data.get("display_name_prefixed")
        self.subscribers = data.get("subscribers")
        self.pub_desc = data.get("public_description")
        self.full_url = "https://reddit.com" + data.get("url")
        self.created = data.get("created_utc")
        self.nsfw = data.get("over18", False)


class Redditor:
    __slots__ = (
        "tdata",
        "adata",
        "subreddit",
        "is_gold",
        "icon_url",
        "link_karma",
        "comment_karma",
        "name",
        "created",
        "is_suspended",
    )
    """Wraps up a Redditor's JSON"""

    def __init__(self, *, about_data, trophy_data=None):
        about_data = about_data.get("data")
        self.tdata = trophy_data.get("data") if trophy_data else None
        self.adata = about_data
        self.name = about_data.get("name")
        self.is_suspended = about_data.get("is_suspended")
        if not self.is_suspended:
            self.subreddit = Subreddit(about_data.get("subreddit"))
            self.is_gold = about_data.get("is_gold")
            self.icon_url = about_data.get("icon_img")
            self.link_karma = about_data.get("link_karma")
            self.comment_karma = about_data.get("comment_karma")
            self.created = about_data.get("created_utc")

    @property
    def trophies(self):
        if not self.tdata:
            return None
        for trophy in self.tdata.get("trophies"):
            yield trophy["data"].get("name")

    def is_cakeday(self):
        return datetime.utcfromtimestamp(self.created).day == datetime.utcnow().day

    @property
    def display_name(self):
        if self.subreddit.title != self.name:
            return self.subreddit.title
        return self.name
