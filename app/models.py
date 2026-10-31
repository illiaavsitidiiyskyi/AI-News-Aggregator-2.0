"""Domain models for aggregated news items."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class NewsItem:
    """A single news article or post."""

    title: str
    url: str
    source: str
    published_at: datetime | None = None
    summary: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)
