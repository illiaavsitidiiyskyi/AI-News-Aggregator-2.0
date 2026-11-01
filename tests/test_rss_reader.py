"""Tests for the single-feed reader (app.rss_reader)."""

from __future__ import annotations

import io

from app.rss_reader import print_articles

FEED_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Test Feed</title>
    <item>
      <title>First &amp; foremost</title>
      <link>https://example.com/1</link>
      <pubDate>Wed, 29 Oct 2026 10:00:00 GMT</pubDate>
      <description>Hello &lt;b&gt;world&lt;/b&gt;!</description>
    </item>
    <item>
      <title>Second</title>
      <link>https://example.com/2</link>
    </item>
  </channel>
</rss>
"""


def _write_feed(tmp_path) -> str:
    feed_file = tmp_path / "feed.xml"
    feed_file.write_text(FEED_XML, encoding="utf-8")
    return str(feed_file)


def test_print_articles_prints_all_items(tmp_path) -> None:
    out = io.StringIO()
    count = print_articles(_write_feed(tmp_path), file=out)
    text = out.getvalue()
    assert count == 2
    assert "First & foremost" in text
    assert "https://example.com/1" in text
    assert "Second" in text


def test_print_articles_strips_html_from_summary(tmp_path) -> None:
    out = io.StringIO()
    print_articles(_write_feed(tmp_path), file=out)
    assert "<b>" not in out.getvalue()
    assert "Hello world!" in out.getvalue()


def test_print_articles_honors_limit(tmp_path) -> None:
    out = io.StringIO()
    count = print_articles(_write_feed(tmp_path), limit=1, file=out)
    text = out.getvalue()
    assert count == 1
    assert "First & foremost" in text
    assert "Second" not in text


def test_print_articles_handles_empty_feed(tmp_path) -> None:
    empty = tmp_path / "empty.xml"
    empty.write_text(
        '<?xml version="1.0"?><rss version="2.0"><channel><title>Empty</title></channel></rss>',
        encoding="utf-8",
    )
    out = io.StringIO()
    count = print_articles(str(empty), file=out)
    assert count == 0
    assert "No articles found" in out.getvalue()
