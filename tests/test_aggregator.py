"""Tests for the Aggregator pipeline."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.aggregator import Aggregator
from app.models import NewsItem
from app.sources.base import NewsSource


class FakeSource(NewsSource):
    """In-memory source for testing."""

    def __init__(self, name: str, items: list[NewsItem], fail: bool = False) -> None:
        self.name = name
        self.items = items
        self.fail = fail

    def fetch(self, limit: int = 50):
        if self.fail:
            raise RuntimeError(f"{self.name} is down")
        return self.items[:limit]


def _item(title: str, url: str, published_at: datetime | None = None) -> NewsItem:
    return NewsItem(title=title, url=url, source="test", published_at=published_at)


NOW = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)


def test_collect_sorts_newest_first() -> None:
    source = FakeSource(
        "s",
        [
            _item("old", "http://a/1", NOW - timedelta(days=2)),
            _item("new", "http://a/2", NOW),
            _item("mid", "http://a/3", NOW - timedelta(days=1)),
        ],
    )
    result = Aggregator([source]).collect()
    assert [i.title for i in result] == ["new", "mid", "old"]


def test_collect_deduplicates_by_url() -> None:
    item = _item("same", "http://a/1", NOW)
    other = _item("other", "http://a/2", NOW)
    s1 = FakeSource("s1", [item])
    s2 = FakeSource("s2", [item, other])
    result = Aggregator([s1, s2]).collect()
    assert len(result) == 2


def test_items_without_date_go_last() -> None:
    source = FakeSource(
        "s",
        [
            _item("undated", "http://a/1"),
            _item("dated", "http://a/2", NOW),
        ],
    )
    result = Aggregator([source]).collect()
    assert [i.title for i in result] == ["dated", "undated"]


def test_naive_and_aware_dates_sort_together() -> None:
    source = FakeSource(
        "s",
        [
            _item("naive", "http://a/1", NOW.replace(tzinfo=None) - timedelta(hours=1)),
            _item("aware", "http://a/2", NOW),
        ],
    )
    result = Aggregator([source]).collect()
    assert [i.title for i in result] == ["aware", "naive"]


def test_failing_source_is_skipped() -> None:
    good = FakeSource("good", [_item("ok", "http://a/1", NOW)])
    bad = FakeSource("bad", [], fail=True)
    result = Aggregator([bad, good]).collect()
    assert len(result) == 1
    assert result[0].title == "ok"
