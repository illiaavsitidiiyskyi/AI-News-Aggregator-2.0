"""Read a single RSS/Atom feed via feedparser and print its articles.

Usage:
    python -m app.rss_reader [FEED_URL] [--limit N]
"""

from __future__ import annotations

import argparse
import re
import sys
from html import unescape
from typing import TextIO

from app.models import NewsItem
from app.sources.rss import RssSource

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


def print_articles(feed_url: str, limit: int = 50, file: TextIO | None = None) -> int:
    """Fetch one feed and print its articles; return the number printed."""
    out = file or sys.stdout
    source = RssSource(feed_url)
    count = 0
    for item in source.fetch(limit=limit):
        print(format_article(item, count + 1), file=out)
        print(file=out)
        count += 1
    if count == 0:
        print(f"No articles found in {feed_url}", file=out)
    return count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Print articles from a single RSS/Atom feed.")
    parser.add_argument("feed_url", nargs="?", default=DEFAULT_FEED_URL, help="feed URL to read")
    parser.add_argument("--limit", type=int, default=50, help="max articles to print (default: 50)")
    args = parser.parse_args(argv)
    print_articles(args.feed_url, limit=args.limit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
