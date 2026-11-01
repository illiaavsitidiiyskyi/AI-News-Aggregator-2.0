"""RSS/Atom feed source with timeout, retry and broken-feed handling."""

from __future__ import annotations

import logging
import time
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from time import struct_time
from typing import Any

import feedparser
import requests

from app.models import NewsItem
from app.normalization import clean_html, normalize_datetime, normalize_text
from app.sources.base import NewsSource

logger = logging.getLogger(__name__)

#: Sent as User-Agent; some feeds reject the default urllib one.
USER_AGENT = (
    "ai-news-aggregator/2.0 (+https://github.com/illiaavsitidiiyskyi/AI-News-Aggregator-2.0)"
)

#: HTTP statuses worth retrying (rate limits and server errors).
RETRYABLE_STATUSES = {429, 500, 502, 503, 504}


class FeedError(Exception):
    """Base class for feed fetching/parsing failures."""


class FeedFetchError(FeedError):
    """Network failure, timeout or non-retryable HTTP error status."""


class FeedParseError(FeedError):
    """The response could not be parsed as RSS/Atom."""


def _entry_datetime(entry: Any) -> datetime | None:
    """Publication datetime as aware UTC (feedparser's struct_time is already UTC)."""
    parsed: struct_time | None = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed is None:
        return None
    return normalize_datetime(datetime(*parsed[:6], tzinfo=timezone.utc))


class RssSource(NewsSource):
    """Fetches items from a single RSS/Atom feed URL.

    Downloads are done with a timeout and retried with exponential backoff;
    malformed feeds raise :class:`FeedParseError` instead of silently yielding
    nothing. HTTP 4xx errors are not retried (a client error won't go away).
    """

    def __init__(
        self,
        url: str,
        name: str | None = None,
        timeout: float = 10.0,
        retries: int = 3,
        backoff_seconds: float = 1.0,
    ) -> None:
        self.url = url
        self.name = name or url
        self._name_from_feed = name is None
        self.timeout = timeout
        self.retries = max(1, retries)
        self.backoff_seconds = backoff_seconds

    def fetch(self, limit: int = 50) -> Iterable[NewsItem]:
        feed = feedparser.parse(self._download())
        if feed.bozo and not feed.entries:
            # Unrecoverably broken body: nothing was parsed — surface the error.
            raise FeedParseError(f"Malformed feed {self.url}: {feed.bozo_exception}")
        if feed.bozo:
            # Recoverable glitches: some entries parsed, report and continue.
            logger.warning(
                "Feed %s is malformed (%s) but %d entries were parsed",
                self.url,
                feed.bozo_exception,
                len(feed.entries),
            )
        if self._name_from_feed:
            # Prefer the feed's own title (human-readable) for storage/reporting.
            feed_title = feed.feed.get("title")
            if feed_title:
                self.name = normalize_text(feed_title)
        for entry in feed.entries[:limit]:
            yield NewsItem(
                title=normalize_text(entry.get("title", "")),
                url=normalize_text(entry.get("link", "")),
                source=self.name,
                published_at=_entry_datetime(entry),
                summary=clean_html(entry.get("summary", "")),
            )

    def _download(self) -> bytes:
        """Download feed bytes with timeout + retry; local files are read directly."""
        if not self.url.startswith(("http://", "https://")):
            try:
                return Path(self.url).read_bytes()
            except OSError as exc:
                raise FeedFetchError(f"Cannot read feed file {self.url}: {exc}") from exc
        last_error: Exception | None = None
        for attempt in range(1, self.retries + 1):
            try:
                response = requests.get(
                    self.url, timeout=self.timeout, headers={"User-Agent": USER_AGENT}
                )
                if response.status_code in RETRYABLE_STATUSES:
                    last_error = FeedFetchError(f"HTTP {response.status_code} from {self.url}")
                elif not response.ok:
                    # 4xx is a client error — retrying will not help.
                    raise FeedFetchError(f"HTTP {response.status_code} from {self.url}")
                else:
                    return response.content
            except requests.RequestException as exc:
                last_error = exc
            if attempt < self.retries:
                delay = self.backoff_seconds * (2 ** (attempt - 1))
                logger.warning(
                    "Fetch attempt %d/%d for %s failed (%s); retrying in %.1fs",
                    attempt,
                    self.retries,
                    self.url,
                    last_error,
                    delay,
                )
                time.sleep(delay)
        raise FeedFetchError(
            f"Failed to fetch {self.url} after {self.retries} attempt(s): {last_error}"
        ) from last_error
