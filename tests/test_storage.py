"""Tests for the storage layer (SQLite stand-in for PostgreSQL)."""

from __future__ import annotations

from datetime import datetime, timezone

from app.models import NewsItem
from app.storage import list_items, save_items

NOW = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)


def _item(title: str, url: str, published_at: datetime | None = NOW) -> NewsItem:
    return NewsItem(title=title, url=url, source="test", published_at=published_at)


def test_save_and_list(db_session) -> None:
    items = [_item("a", "http://a/1"), _item("b", "http://a/2")]
    assert save_items(db_session, items) == 2
    db_session.commit()

    result = list_items(db_session)
    assert [r.title for r in result] == ["b", "a"]  # newest first


def test_save_skips_duplicate_urls(db_session) -> None:
    assert save_items(db_session, [_item("a", "http://a/1")]) == 1
    db_session.commit()
    assert save_items(db_session, [_item("a-renamed", "http://a/1")]) == 0
    db_session.commit()

    result = list_items(db_session)
    assert len(result) == 1
    assert result[0].title == "a"  # original kept


def test_save_ignores_items_without_url(db_session) -> None:
    assert save_items(db_session, [_item("no-url", "")]) == 0
    db_session.commit()
    assert list_items(db_session) == []


def test_items_without_date_go_last(db_session) -> None:
    save_items(db_session, [_item("undated", "http://a/1", None), _item("dated", "http://a/2")])
    db_session.commit()
    result = list_items(db_session)
    assert [r.title for r in result] == ["dated", "undated"]
