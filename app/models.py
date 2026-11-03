"""Domain models for aggregated news items."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urlsplit, urlunsplit


@dataclass(frozen=True)
class NewsItem:
    """A single news article or post as fetched from a source."""

    title: str
    url: str
    source: str
    published_at: datetime | None = None
    summary: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)


def normalize_url(url: str) -> str:
    """Normalize a URL for dedup: lowercase scheme/host, drop fragment and trailing slash.

    The result is stored in ``articles.normalized_url`` and guarded by a unique
    index, so it is the canonical dedup key across sources.
    """
    parts = urlsplit(url.strip())
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, parts.query, ""))
