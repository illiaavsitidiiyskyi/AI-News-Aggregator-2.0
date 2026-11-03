"""Tests for data normalization: HTML cleanup, text/encoding and datetime handling."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.db_models import Article
from app.models import NewsItem
from app.normalization import clean_html, normalize_datetime, normalize_text
from app.sources.rss import RssSource
from app.storage import save_items

UTC = timezone.utc


# --- clean_html ---------------------------------------------------------------


def test_clean_html_strips_tags() -> None:
    assert clean_html("<p>Hello <b>world</b>!</p>") == "Hello world!"


def test_clean_html_removes_script_and_style() -> None:
    text = "before<script>alert('x')</script>after<style>.a{}</style>end"
    assert clean_html(text) == "before after end"


def test_clean_html_unescapes_entities() -> None:
    assert clean_html("Fish &amp; chips &mdash; yum") == "Fish & chips — yum"


def test_clean_html_unescapes_double_encoded_markup() -> None:
    # Some feeds escape their own HTML: &lt;b&gt;... must not survive as literal tags.
    assert clean_html("A &lt;i&gt;little&lt;/i&gt; nest") == "A little nest"


def test_clean_html_collapses_whitespace() -> None:
    assert clean_html("  a \n\t b   c  ") == "a b c"
    assert clean_html("<p>a</p>\n\n<p>b</p>") == "a b"


def test_clean_html_handles_empty_and_none() -> None:
    assert clean_html("") == ""
    assert clean_html(None) == ""  # type: ignore[arg-type]


def test_clean_html_is_idempotent() -> None:
    once = clean_html("<p>Hello <b>world</b> &amp; friends</p>")
    assert clean_html(once) == once


# --- normalize_text -----------------------------------------------------------


def test_normalize_text_decodes_bytes() -> None:
    assert normalize_text("привет".encode()) == "привет"
    # Invalid UTF-8 is replaced, not raised.
    assert "\ufffd" in normalize_text(b"\xff\xfe broken")


def test_normalize_text_strips_zero_width_and_control_chars() -> None:
    assert normalize_text("a\u200bb\ufeffc") == "abc"
    assert normalize_text("a\x00b\x07c") == "a b c"


def test_normalize_text_nfc_and_whitespace() -> None:
    # "е" as e + combining accent -> single codepoint after NFC.
    assert normalize_text("  spaced\u00a0out  ") == "spaced out"
    assert normalize_text(None) == ""  # type: ignore[arg-type]


# --- normalize_datetime -------------------------------------------------------


def test_normalize_datetime_naive_assumed_utc() -> None:
    naive = datetime(2026, 10, 31, 12, 0)
    assert normalize_datetime(naive) == datetime(2026, 10, 31, 12, 0, tzinfo=UTC)


def test_normalize_datetime_converts_to_utc() -> None:
    msk = timezone(timedelta(hours=3))
    aware = datetime(2026, 10, 31, 15, 0, tzinfo=msk)
    assert normalize_datetime(aware) == datetime(2026, 10, 31, 12, 0, tzinfo=UTC)


def test_normalize_datetime_none() -> None:
    assert normalize_datetime(None) is None


# --- integration: source ------------------------------------------------------


def test_rss_source_normalizes_title_summary_and_date(tmp_path) -> None:
    feed = tmp_path / "feed.xml"
    feed.write_text(
        '<?xml version="1.0" encoding="utf-8"?>'
        "<rss version=\"2.0\"><channel><title>  Feed \u200b Name  </title>"
        "<item>"
        "<title>  Hello \u200b &amp; goodbye </title>"
        "<link> https://example.com/a </link>"
        "<pubDate>Thu, 29 Oct 2026 13:00:00 +0300</pubDate>"
        "<description>&lt;p&gt;Text &lt;b&gt;bold&lt;/b&gt;.&lt;/p&gt;</description>"
        "</item></channel></rss>",
        encoding="utf-8",
    )
    item = next(iter(RssSource(str(feed)).fetch()))

    assert item.title == "Hello & goodbye"
    assert item.url == "https://example.com/a"
    assert item.summary == "Text bold."
    # +0300 13:00 normalized to UTC 10:00.
    assert item.published_at == datetime(2026, 10, 29, 10, 0, tzinfo=UTC)
    assert item.source == "Feed Name"


def test_rss_source_parses_non_utf8_feed(tmp_path) -> None:
    # windows-1251 feed: feedparser honors the XML declaration.
    feed = tmp_path / "cp1251.xml"
    feed.write_bytes(
        '<?xml version="1.0" encoding="windows-1251"?>'
        '<rss version="2.0"><channel><title>Kan\u0430l</title>'
        "<item><title>\u041d\u043e\u0432\u043e\u0441\u0442\u044c \u0434\u043d\u044f</title>"
        "<link>https://example.com/ru</link></item>"
        "</channel></rss>".encode("windows-1251")
    )
    item = next(iter(RssSource(str(feed)).fetch()))
    assert item.title == "Новость дня"


def test_rss_source_handles_missing_date(tmp_path) -> None:
    feed = tmp_path / "nodate.xml"
    feed.write_text(
        '<?xml version="1.0"?><rss version="2.0"><channel><title>F</title>'
        "<item><title>A</title><link>https://e.com/a</link></item>"
        "</channel></rss>",
        encoding="utf-8",
    )
    item = next(iter(RssSource(str(feed)).fetch()))
    assert item.published_at is None


# --- integration: storage -----------------------------------------------------


def test_storage_normalizes_on_save(db_session) -> None:
    item = NewsItem(
        title="  Padded \u200b title  ",
        url=" https://example.com/x ",
        source="s",
        summary="<p>Body <em>text</em> &amp; more</p>",
        published_at=datetime(2026, 10, 31, 15, 0, tzinfo=timezone(timedelta(hours=3))),
    )
    save_items(db_session, [item])
    db_session.commit()

    article = db_session.scalar(select(Article))
    assert article.title == "Padded title"
    assert article.url == "https://example.com/x"
    assert article.normalized_url == "https://example.com/x"
    assert article.content == "Body text & more"
    # SQLite drops tzinfo on read-back; normalize before comparing.
    assert normalize_datetime(article.published_at) == datetime(2026, 10, 31, 12, 0, tzinfo=UTC)


def test_storage_normalizes_naive_date_to_utc(db_session) -> None:
    save_items(
        db_session,
        [
            NewsItem(
                title="a",
                url="https://example.com/n",
                source="s",
                published_at=datetime(2026, 10, 31, 12, 0),  # naive
            )
        ],
    )
    db_session.commit()
    article = db_session.scalar(select(Article))
    assert normalize_datetime(article.published_at) == datetime(2026, 10, 31, 12, 0, tzinfo=UTC)
