"""Aggregation pipeline: fetch from sources, deduplicate, sort."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from datetime import timezone

from app.config import Config
from app.models import NewsItem
from app.sources.base import NewsSource

logger = logging.getLogger(__name__)

#: Called after each source fetch: (source, fetched item count, error or None).
SourceResultHook = Callable[[NewsSource, int, Exception | None], None]


class Aggregator:
    """Coordinates fetching and merging news from multiple sources."""

    def __init__(
        self,
        sources: Iterable[NewsSource],
        config: Config | None = None,
        on_source_result: SourceResultHook | None = None,
    ) -> None:
        self.sources = list(sources)
        self.config = config or Config()
        self.on_source_result = on_source_result

    def collect(self) -> list[NewsItem]:
        """Fetch all sources, deduplicate by URL and return items newest first."""
        items: list[NewsItem] = []
        for source in self.sources:
            try:
                fetched = list(source.fetch(limit=self.config.max_items_per_source))
            except Exception as exc:
                logger.exception("Failed to fetch from source %s", source.name)
                self._notify(source, 0, exc)
            else:
                items.extend(fetched)
                self._notify(source, len(fetched), None)
        return self._deduplicate(items)

    def _notify(self, source: NewsSource, count: int, error: Exception | None) -> None:
        if self.on_source_result is None:
            return
        try:
            self.on_source_result(source, count, error)
        except Exception:
            # Status recording must never break the collection pipeline.
            logger.exception("on_source_result hook failed for source %s", source.name)

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
