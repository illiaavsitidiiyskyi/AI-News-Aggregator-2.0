"""Tests for the Aggregator pipeline."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.aggregator import Aggregator
from app.models import NewsItem, titles_similar
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


def test_collect_deduplicates_similar_titles_across_sources() -> None:
    # Same story, different URLs and a publisher suffix: fuzzy match collapses it.
    s1 = FakeSource("s1", [_item("OpenAI releases GPT-5 model", "http://a/1", NOW)])
    s2 = FakeSource("s2", [_item("OpenAI releases GPT-5 model | TechCrunch", "http://b/2", NOW)])
    result = Aggregator([s1, s2]).collect()
    assert [i.title for i in result] == ["OpenAI releases GPT-5 model"]


def test_collect_keeps_titles_that_differ_by_number() -> None:
    # Version numbers distinguish news: GPT-5 and GPT-5.2 are different items.
    s1 = FakeSource("s1", [_item("OpenAI releases GPT-5", "http://a/1", NOW)])
    s2 = FakeSource("s2", [_item("OpenAI releases GPT-5.2", "http://b/2", NOW)])
    assert len(Aggregator([s1, s2]).collect()) == 2


def test_collect_keeps_distinct_stories_about_the_same_subject() -> None:
    # Same subject, different aspect: below the similarity threshold on purpose.
    s1 = FakeSource("s1", [_item("OpenAI announces GPT-5 pricing", "http://a/1", NOW)])
    s2 = FakeSource("s2", [_item("OpenAI announces GPT-5 release date", "http://b/2", NOW)])
    assert len(Aggregator([s1, s2]).collect()) == 2


def test_titles_similar_ignores_case_punctuation_and_order() -> None:
    assert titles_similar("OpenAI releases GPT-5!", "openai releases gpt-5")
    assert titles_similar("GPT-5 is here: OpenAI says", "OpenAI says: GPT-5 is here")


def test_titles_similar_tolerates_publisher_suffix() -> None:
    assert titles_similar("Big news from OpenAI", "Big news from OpenAI | TechCrunch")


def test_titles_similar_rejects_different_numbers() -> None:
    assert not titles_similar("Top 10 AI tools", "Top 5 AI tools")
    assert not titles_similar("OpenAI releases GPT-5", "OpenAI releases GPT-5.2")


def test_titles_similar_rejects_unrelated_or_empty_titles() -> None:
    assert not titles_similar("OpenAI releases GPT-5", "Google releases Gemini 4")
    assert not titles_similar("", "anything at all")
    assert not titles_similar("", "")
