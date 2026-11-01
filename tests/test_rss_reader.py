"""Tests for the single-feed reader (app.rss_reader)."""

from __future__ import annotations

import io
from datetime import datetime

from sqlalchemy import func, select

from app.db_models import Article, Source
from app.rss_reader import fetch_articles, print_articles, run
from app.sources.rss import RssSource

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


def _source(feed_url: str) -> RssSource:
    return RssSource(feed_url, retries=1, backoff_seconds=0)


def test_fetch_articles_returns_feed_items(tmp_path) -> None:
    items = fetch_articles(_source(_write_feed(tmp_path)))
    assert [i.title for i in items] == ["First & foremost", "Second"]
    assert all(i.source == "Test Feed" for i in items)  # source name = feed title


def test_print_articles_prints_all_items(tmp_path) -> None:
    out = io.StringIO()
    print_articles(fetch_articles(_source(_write_feed(tmp_path))), file=out)
    text = out.getvalue()
    assert "First & foremost" in text
    assert "https://example.com/1" in text
    assert "Second" in text


def test_print_articles_strips_html_from_summary(tmp_path) -> None:
    out = io.StringIO()
    print_articles(fetch_articles(_source(_write_feed(tmp_path))), file=out)
    assert "<b>" not in out.getvalue()
    assert "Hello world!" in out.getvalue()


def test_fetch_honors_limit(tmp_path) -> None:
    out = io.StringIO()
    print_articles(fetch_articles(_source(_write_feed(tmp_path)), limit=1), file=out)
    text = out.getvalue()
    assert "First & foremost" in text
    assert "Second" not in text


def test_print_articles_handles_empty_feed(tmp_path) -> None:
    empty = tmp_path / "empty.xml"
    empty.write_text(
        '<?xml version="1.0"?><rss version="2.0"><channel><title>Empty</title></channel></rss>',
        encoding="utf-8",
    )
    out = io.StringIO()
    print_articles(fetch_articles(_source(str(empty))), file=out)
    assert "No articles found" in out.getvalue()


def test_run_saves_articles_and_source(db_session, tmp_path) -> None:
    feed_url = _write_feed(tmp_path)
    assert run(feed_url, file=io.StringIO()) == 0

    articles = db_session.scalars(select(Article)).all()
    assert sorted(a.title for a in articles) == ["First & foremost", "Second"]

    source = db_session.scalar(select(Source))
    assert source is not None
    assert source.name == "Test Feed"  # source stored in `sources` by feed title
    assert source.url == feed_url
    assert all(a.source_id == source.id for a in articles)


def test_run_skips_duplicates_on_rerun(db_session, tmp_path) -> None:
    feed_url = _write_feed(tmp_path)
    run(feed_url, file=io.StringIO())
    out = io.StringIO()
    run(feed_url, file=out)

    assert db_session.scalar(select(func.count()).select_from(Article)) == 2
    assert db_session.scalar(select(func.count()).select_from(Source)) == 1
    assert "Saved 0 new article(s)" in out.getvalue()


def test_run_without_save_keeps_db_empty(db_session, tmp_path) -> None:
    run(_write_feed(tmp_path), save=False, file=io.StringIO())
    assert db_session.scalars(select(Article)).all() == []
    assert db_session.scalars(select(Source)).all() == []


def test_run_records_success_status(db_session, tmp_path) -> None:
    run(_write_feed(tmp_path), file=io.StringIO())

    source = db_session.scalar(select(Source))
    assert source.last_fetched_at is not None
    assert isinstance(source.last_fetched_at, datetime)
    assert source.last_error is None
    assert source.failure_count == 0
    assert source.is_active is True


def test_run_records_failure_and_returns_nonzero(db_session, tmp_path) -> None:
    missing = tmp_path / "missing.xml"  # unreadable file -> FeedFetchError
    err_out = io.StringIO()
    exit_code = run(str(missing), file=err_out)

    assert exit_code == 1
    source = db_session.scalar(select(Source))
    assert source is not None
    assert source.url == str(missing)
    assert source.last_fetched_at is None
    assert source.last_error is not None and "Cannot read feed file" in source.last_error
    assert source.failure_count == 1
    assert source.is_active is True  # still active: one failure isn't enough


def test_run_failure_does_not_raise_with_db_errors(db_session, tmp_path, monkeypatch) -> None:
    # A failing fetch + failing status recording must not crash the reader.
    from app import rss_reader

    def broken_record(*args, **kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(rss_reader, "_record_outcome", broken_record)
    missing = tmp_path / "missing.xml"
    assert run(str(missing), file=io.StringIO()) == 1


def test_run_no_save_does_not_touch_source_status(db_session, tmp_path) -> None:
    missing = tmp_path / "missing.xml"
    assert run(str(missing), save=False, file=io.StringIO()) == 1
    assert db_session.scalars(select(Source)).all() == []
