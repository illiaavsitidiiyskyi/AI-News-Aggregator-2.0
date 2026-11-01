"""Read a single RSS/Atom feed via feedparser, print its articles and save them to the DB.

The feed itself is registered in the ``sources`` table (name = feed title, url = feed URL),
each article is stored in ``articles`` and deduplicated by URL hash.

Usage:
    python -m app.rss_reader [FEED_URL] [--limit N] [--no-save]
"""

from __future__ import annotations

import argparse
import re
import sys
from html import unescape
from typing import TextIO

from app.db import get_session_factory
from app.models import NewsItem
from app.sources.rss import RssSource
from app.storage import get_or_create_source, save_items

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


def fetch_articles(feed_url: str, limit: int = 50) -> list[NewsItem]:
    """Fetch up to ``limit`` articles from a single feed."""
    return list(RssSource(feed_url).fetch(limit=limit))


def print_articles(items: list[NewsItem], file: TextIO | None = None) -> None:
    """Print fetched articles to stdout (or ``file``)."""
    out = file or sys.stdout
    for index, item in enumerate(items, start=1):
        print(format_article(item, index), file=out)
        print(file=out)
    if not items:
        print("No articles found.", file=out)


def save_to_db(feed_url: str, items: list[NewsItem]) -> int:
    """Persist articles; register the feed in the ``sources`` table. Returns new rows count."""
    if not items:
        return 0
    session = get_session_factory()()
    try:
        # All items come from the same feed: register it with a human-readable name + URL.
        get_or_create_source(session, items[0].source, url=feed_url)
        saved = save_items(session, items)
        session.commit()
        return saved
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def run(feed_url: str, limit: int = 50, save: bool = True, file: TextIO | None = None) -> None:
    """Fetch one feed, print its articles and (unless ``save`` is off) store them in the DB."""
    items = fetch_articles(feed_url, limit=limit)
    print_articles(items, file=file)
    if not save:
        return
    saved = save_to_db(feed_url, items)
    out = file or sys.stdout
    if items:
        print(f"Saved {saved} new article(s) to the database.", file=out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Print articles from a single RSS/Atom feed and save them to the database."
    )
    parser.add_argument("feed_url", nargs="?", default=DEFAULT_FEED_URL, help="feed URL to read")
    parser.add_argument("--limit", type=int, default=50, help="max articles to print (default: 50)")
    parser.add_argument(
        "--no-save", action="store_true", help="only print articles, do not touch the database"
    )
    args = parser.parse_args(argv)
    try:
        run(args.feed_url, limit=args.limit, save=not args.no_save)
    except Exception as exc:  # noqa: BLE001 — CLI boundary: report any failure and exit non-zero
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
