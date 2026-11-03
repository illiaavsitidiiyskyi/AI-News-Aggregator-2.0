"""Domain models for aggregated news items."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urlsplit, urlunsplit

from app.normalization import normalize_text


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


def compute_content_hash(title: str, content: str) -> str | None:
    """sha256 of the normalized title and content — dedup key across different URLs.

    Catches the same material syndicated under a new URL: the URL key cannot see
    it, but identical title+content can. Returns ``None`` when ``content`` is
    empty — a title alone is too weak a signal (generic titles collide across
    genuinely different articles), so such items are deduplicated by URL only.
    NULLs never conflict in a unique index, so the guard needs no special case.
    """
    title = normalize_text(title)
    content = normalize_text(content)
    if not content:
        return None
    return hashlib.sha256(f"{title}\n{content}".encode()).hexdigest()
