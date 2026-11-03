"""Aggregation pipeline: fetch from sources, deduplicate (URL + fuzzy titles), sort."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable

from app.config import Config
from app.models import NewsItem, titles_similar
from app.normalization import normalize_datetime
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
        """Fetch all sources, deduplicate (exact URL, fuzzy title) and return items newest first."""
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
        """Drop repeat URLs and near-identical titles; keep the rest newest first.

        Exact URL equality first (cheap), then fuzzy title comparison
        (``titles_similar``) so the same story published by different sources
        under different URLs collapses into one item — the first occurrence
        wins. Items without a URL skip the URL check but still go through the
        title check. Pairwise comparison is O(n²) over a per-run batch, which
        stays small (sources × max_items_per_source).
        """
        seen_urls: set[str] = set()
        unique: list[NewsItem] = []
        for item in items:
            if item.url:
                if item.url in seen_urls:
                    continue
                seen_urls.add(item.url)
            if any(titles_similar(item.title, kept.title) for kept in unique):
                continue
            unique.append(item)
        # Newest first; items without a date go last.
        unique.sort(key=_sort_key, reverse=True)
        return unique


def _sort_key(item: NewsItem) -> tuple[int, float]:
    """Sort key handling missing and naive/aware datetimes uniformly.

    Used with ``reverse=True``: dated items come first (newest first),
    items without a date go last. ``normalize_datetime`` makes naive values
    UTC-aware so timestamps compare correctly.
    """
    dt = normalize_datetime(item.published_at)
    if dt is None:
        return (0, 0.0)
    return (1, dt.timestamp())
