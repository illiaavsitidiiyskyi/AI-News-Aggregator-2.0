"""RSS/Atom feed source."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone
from time import struct_time
from typing import Any

import feedparser

from app.models import NewsItem
from app.sources.base import NewsSource


def _entry_datetime(entry: Any) -> datetime | None:
    parsed: struct_time | None = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed is None:
        return None
    return datetime(*parsed[:6], tzinfo=timezone.utc)


class RssSource(NewsSource):
    """Fetches items from a single RSS/Atom feed URL."""

    def __init__(self, url: str, name: str | None = None) -> None:
        self.url = url
        self.name = name or url

    def fetch(self, limit: int = 50) -> Iterable[NewsItem]:
        feed = feedparser.parse(self.url)
        for entry in feed.entries[:limit]:
            yield NewsItem(
                title=entry.get("title", ""),
                url=entry.get("link", ""),
                source=self.name,
                published_at=_entry_datetime(entry),
                summary=entry.get("summary", ""),
            )
