"""News sources (RSS feeds, APIs, scrapers)."""

from app.sources.base import NewsSource
from app.sources.rss import RssSource

__all__ = ["NewsSource", "RssSource"]
