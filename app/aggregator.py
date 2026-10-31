"""Aggregation pipeline: fetch from sources, deduplicate, sort."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import timezone

from app.config import Config
from app.models import NewsItem
from app.sources.base import NewsSource

logger = logging.getLogger(__name__)


class Aggregator:
    """Coordinates fetching and merging news from multiple sources."""

    def __init__(self, sources: Iterable[NewsSource], config: Config | None = None) -> None:
        self.sources = list(sources)
        self.config = config or Config()

    def collect(self) -> list[NewsItem]:
        """Fetch all sources, deduplicate by URL and return items newest first."""
        items: list[NewsItem] = []
        for source in self.sources:
            try:
                items.extend(source.fetch(limit=self.config.max_items_per_source))
            except Exception:
                logger.exception("Failed to fetch from source %s", source.name)
        return self._deduplicate(items)

    @staticmethod
    def _deduplicate(items: Iterable[NewsItem]) -> list[NewsItem]:
        seen: set[str] = set()
        unique: list[NewsItem] = []
        for item in items:
            if item.url:
                if item.url in seen:
                    continue
                seen.add(item.url)
            unique.append(item)
        # Newest first; items without a date go last.
        unique.sort(key=_sort_key, reverse=True)
        return unique


def _sort_key(item: NewsItem) -> tuple[int, float]:
    """Sort key handling missing and naive/aware datetimes uniformly.

    Used with ``reverse=True``: dated items come first (newest first),
    items without a date go last.
    """
    dt = item.published_at
    if dt is None:
        return (0, 0.0)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (1, dt.timestamp())
