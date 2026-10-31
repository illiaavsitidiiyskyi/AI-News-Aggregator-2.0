"""Abstract base class for news sources."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable

from app.models import NewsItem


class NewsSource(ABC):
    """A source of news items (RSS feed, API, scraper, ...)."""

    #: Human-readable source name, overridden by subclasses.
    name: str = "base"

    @abstractmethod
    def fetch(self, limit: int = 50) -> Iterable[NewsItem]:
        """Fetch up to ``limit`` news items, newest first."""
        raise NotImplementedError
