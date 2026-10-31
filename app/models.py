"""Domain models for aggregated news items."""

from __future__ import annotations

import hashlib
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
    """Normalize a URL for dedup: lowercase scheme/host, drop fragment and trailing slash."""
    parts = urlsplit(url.strip())
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, parts.query, ""))


def compute_hash(url: str) -> str:
    """sha256 hex digest of the normalized URL — dedup key stored on Article.hash."""
    return hashlib.sha256(normalize_url(url).encode("utf-8")).hexdigest()
