"""Read a single RSS/Atom feed via feedparser, print its articles and save them to the DB.

The feed itself is registered in the ``sources`` table (name = feed title, url = feed URL),
each article is stored in ``articles`` and deduplicated by URL hash. Fetch outcomes are
tracked on the source: ``last_fetched_at`` / ``last_error`` / ``is_active``.

Usage:
    python -m app.rss_reader [FEED_URL] [--limit N] [--no-save]
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from html import unescape
from typing import TextIO

from app.config import Config
from app.db import get_session_factory
from app.models import NewsItem
from app.sources.base import NewsSource
from app.sources.rss import RssSource
from app.storage import (
    get_or_create_source,
    record_fetch_failure,
    record_fetch_success,
    save_items,
)

logger = logging.getLogger(__name__)

DEFAULT_FEED_URL = "https://huggingface.co/blog/feed.xml"

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_SPACE_BEFORE_PUNCT_RE = re.compile(r"\s+([,.;:!?])")


def _strip_html(text: str) -> str:
    """Remove HTML tags and collapse whitespace for plain-text output."""
    plain = _WS_RE.sub(" ", unescape(_TAG_RE.sub(" ", text))).strip()
    return _SPACE_BEFORE_PUNCT_RE.sub(r"\1", plain)


def format_article(item: NewsItem, index: int) -> str:
    """Render one article as a plain-text block."""
    dt = item.published_at
    published = dt.strftime("%Y-%m-%d %H:%M") if dt else "unknown date"
    lines = [
        f"{index}. {item.title or '(no title)'}",
        f"   {item.url}" if item.url else "   (no link)",
        f"   {published}",
    ]
    summary = _strip_html(item.summary)
    if summary:
        lines.append(f"   {summary}")
    return "\n".join(lines)


def fetch_articles(source: NewsSource, limit: int = 50) -> list[NewsItem]:
    """Fetch up to ``limit`` articles from a single source."""
    return list(source.fetch(limit=limit))


def print_articles(items: list[NewsItem], file: TextIO | None = None) -> None:
    """Print fetched articles to stdout (or ``file``)."""
    out = file or sys.stdout
    for index, item in enumerate(items, start=1):
        print(format_article(item, index), file=out)
        print(file=out)
    if not items:
        print("No articles found.", file=out)


def save_to_db(feed_url: str, items: list[NewsItem]) -> int:
    """Persist articles and register the feed in ``sources``. Returns new rows count."""
    session = get_session_factory()()
    try:
        if items:
            # All items come from the same feed: register it with its title + URL.
            get_or_create_source(session, items[0].source, url=feed_url)
        saved = save_items(session, items)
        session.commit()
        return saved
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _record_outcome(feed_url: str, source: NewsSource, error: str | None) -> None:
    """Update the source's fetch-status fields; never raises (status is best-effort)."""
    session = get_session_factory()()
    try:
        record = get_or_create_source(session, source.name, url=feed_url)
        if error is None:
            record_fetch_success(session, record)
        else:
            record_fetch_failure(session, record, error)
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("Failed to record fetch outcome for %s", feed_url)
    finally:
        session.close()


def run(
    feed_url: str,
    limit: int = 50,
    save: bool = True,
    file: TextIO | None = None,
    source: NewsSource | None = None,
) -> int:
    """Fetch one feed, print its articles, store them and record the fetch outcome.

    Returns the process exit code: 0 on success, 1 on fetch/parse failure.
    """
    out = file or sys.stdout
    config = Config.from_env()
    source = source or RssSource(
        feed_url,
        timeout=config.feed_timeout_seconds,
        retries=config.feed_retries,
        backoff_seconds=config.feed_retry_backoff_seconds,
    )
    try:
        items = fetch_articles(source, limit=limit)
    except Exception as exc:
        logger.error("Failed to fetch %s: %s", feed_url, exc)
        print(f"Error: {exc}", file=sys.stderr)
        if save:
            _safe_record_outcome(feed_url, source, error=str(exc))
        return 1
    print_articles(items, file=file)
    if save:
        saved = save_to_db(feed_url, items)
        _safe_record_outcome(feed_url, source, error=None)
        if items:
            print(f"Saved {saved} new article(s) to the database.", file=out)
    return 0


def _safe_record_outcome(feed_url: str, source: NewsSource, error: str | None) -> None:
    """Status recording is best-effort: never let it break the reader."""
    try:
        _record_outcome(feed_url, source, error)
    except Exception:
        logger.exception("Failed to record fetch outcome for %s", feed_url)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    parser = argparse.ArgumentParser(
        description="Print articles from a single RSS/Atom feed and save them to the database."
    )
    parser.add_argument("feed_url", nargs="?", default=DEFAULT_FEED_URL, help="feed URL to read")
    parser.add_argument("--limit", type=int, default=50, help="max articles to print (default: 50)")
    parser.add_argument(
        "--no-save", action="store_true", help="only print articles, do not touch the database"
    )
    args = parser.parse_args(argv)
    return run(args.feed_url, limit=args.limit, save=not args.no_save)


if __name__ == "__main__":
    raise SystemExit(main())
