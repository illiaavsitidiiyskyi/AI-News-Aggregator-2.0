"""Tests for the storage layer (SQLite stand-in for PostgreSQL)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, inspect, select

from app.db_models import Article, Source
from app.models import NewsItem, normalize_url
from app.storage import get_or_create_source, list_items, save_items

NOW = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)


def _item(
    title: str, url: str, published_at: datetime | None = NOW, source: str = "test"
) -> NewsItem:
    return NewsItem(title=title, url=url, source=source, published_at=published_at)


def test_save_and_list(db_session) -> None:
    items = [_item("a", "http://a/1"), _item("b", "http://a/2")]
    assert save_items(db_session, items) == 2
    db_session.commit()

    result = list_items(db_session)
    assert [r.title for r in result] == ["b", "a"]  # newest first
    assert all(r.source.name == "test" for r in result)


def test_save_creates_source_and_links_articles(db_session) -> None:
    save_items(db_session, [_item("a", "http://a/1"), _item("b", "http://a/2", source="other")])
    db_session.commit()

    sources = db_session.scalars(select(Source)).all()
    assert sorted(s.name for s in sources) == ["other", "test"]
    article = db_session.scalar(select(Article).where(Article.title == "a"))
    assert article is not None
    assert article.source_id == next(s.id for s in sources if s.name == "test")
    assert article.normalized_url == normalize_url("http://a/1")


def test_get_or_create_source_reuses_existing(db_session) -> None:
    s1 = get_or_create_source(db_session, "feed")
    s2 = get_or_create_source(db_session, "feed")
    db_session.commit()
    assert s1.id == s2.id
    assert db_session.scalar(select(func.count()).select_from(Source)) == 1


def test_save_skips_duplicate_urls(db_session) -> None:
    assert save_items(db_session, [_item("a", "http://a/1")]) == 1
    db_session.commit()
    assert save_items(db_session, [_item("a-renamed", "http://a/1")]) == 0
    db_session.commit()

    result = list_items(db_session)
    assert len(result) == 1
    assert result[0].title == "a"  # original kept


def test_save_dedupes_by_normalized_url(db_session) -> None:
    # Same article under cosmetic URL variants -> same normalized_url -> skipped.
    assert save_items(db_session, [_item("a", "https://Example.com/post/")]) == 1
    db_session.commit()
    assert save_items(db_session, [_item("a", "https://example.com/post")]) == 0
    db_session.commit()
    assert len(list_items(db_session)) == 1


def test_save_dedupes_variants_within_one_batch(db_session) -> None:
    # Duplicates inside a single batch: the savepoint skips only the offender.
    items = [_item("a", "https://Example.com/post/"), _item("a", "https://example.com/post")]
    assert save_items(db_session, items) == 1
    db_session.commit()
    assert len(list_items(db_session)) == 1


def test_normalized_url_has_unique_index(db_session) -> None:
    # The DB, not the application, is the authority on duplicates.
    constraints = inspect(db_session.bind).get_unique_constraints("articles")
    assert any(c["name"] == "uq_articles_normalized_url" for c in constraints)


def test_save_ignores_items_without_url(db_session) -> None:
    assert save_items(db_session, [_item("no-url", "")]) == 0
    db_session.commit()
    assert list_items(db_session) == []


def test_items_without_date_go_last(db_session) -> None:
    save_items(db_session, [_item("undated", "http://a/1", None), _item("dated", "http://a/2")])
    db_session.commit()
    result = list_items(db_session)
    assert [r.title for r in result] == ["dated", "undated"]


def test_normalize_url() -> None:
    assert normalize_url(" https://Example.com/Post/ ") == "https://example.com/Post"
    assert normalize_url("https://example.com/post#section") == "https://example.com/post"


def test_normalize_url_is_stable_and_distinct() -> None:
    assert normalize_url("https://example.com/post/") == normalize_url("https://example.com/post")
    assert normalize_url("https://example.com/a") != normalize_url("https://example.com/b")
