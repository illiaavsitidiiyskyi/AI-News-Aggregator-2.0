"""Tests for failure handling: retries, broken feeds, source status fields."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import requests
from sqlalchemy import select

from app.aggregator import Aggregator
from app.db_models import Source
from app.sources.base import NewsSource
from app.sources.rss import FeedFetchError, FeedParseError, RssSource
from app.storage import (
    MAX_FAILURES_BEFORE_INACTIVE,
    active_sources,
    record_fetch_failure,
    record_fetch_success,
)

GOOD_FEED = b"""<?xml version="1.0"?>
<rss version="2.0"><channel><title>F</title>
<item><title>A</title><link>https://e.com/a</link></item>
</channel></rss>"""


def _response(status_code: int = 200, content: bytes = GOOD_FEED) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.ok = status_code < 400
    resp.content = content
    return resp


def _patch_get(monkeypatch, side_effect) -> list:
    calls: list = []

    def fake_get(url, **kwargs):
        calls.append(kwargs)
        result = side_effect[len(calls) - 1] if len(calls) < len(side_effect) else side_effect[-1]
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(requests, "get", fake_get)
    return calls


def test_fetch_retries_on_timeout_then_succeeds(monkeypatch) -> None:
    timeout = requests.Timeout("timed out")
    calls = _patch_get(monkeypatch, [timeout, timeout, _response()])
    source = RssSource("https://x.com/feed", retries=3, backoff_seconds=0)

    items = list(source.fetch())

    assert [i.title for i in items] == ["A"]
    assert len(calls) == 3
    assert all("timeout" in kwargs for kwargs in calls)  # timeout passed to requests


def test_fetch_respects_timeout_setting(monkeypatch) -> None:
    calls = _patch_get(monkeypatch, [_response()])
    RssSource("https://x.com/feed", timeout=7.5, retries=1).fetch().__next__()
    assert calls[0]["timeout"] == 7.5


def test_fetch_raises_after_retries_exhausted(monkeypatch) -> None:
    _patch_get(monkeypatch, [requests.ConnectionError("refused")] * 3)
    source = RssSource("https://x.com/feed", retries=3, backoff_seconds=0)

    with pytest.raises(FeedFetchError, match="after 3 attempt"):
        list(source.fetch())


def test_fetch_retries_on_server_errors(monkeypatch) -> None:
    calls = _patch_get(monkeypatch, [_response(503), _response()])
    items = list(RssSource("https://x.com/feed", retries=2, backoff_seconds=0).fetch())
    assert len(items) == 1
    assert len(calls) == 2


def test_fetch_does_not_retry_on_404(monkeypatch) -> None:
    calls = _patch_get(monkeypatch, [_response(404), _response()])
    source = RssSource("https://x.com/feed", retries=3, backoff_seconds=0)

    with pytest.raises(FeedFetchError, match="HTTP 404"):
        list(source.fetch())
    assert len(calls) == 1  # client errors are not retried


def test_fetch_raises_on_broken_feed(tmp_path) -> None:
    broken = tmp_path / "broken.xml"
    broken.write_text("this is definitely not xml <<<", encoding="utf-8")
    source = RssSource(str(broken))

    with pytest.raises(FeedParseError, match="Malformed feed"):
        list(source.fetch())


def test_fetch_tolerates_partially_broken_feed(tmp_path) -> None:
    # Unclosed root tag: feedparser recovers the item but flags bozo.
    partial = tmp_path / "partial.xml"
    partial.write_text(
        '<?xml version="1.0"?><rss><channel><title>F</title>'
        "<item><title>A</title><link>https://e.com/a</link></item>",
        encoding="utf-8",
    )
    items = list(RssSource(str(partial)).fetch())
    assert [i.title for i in items] == ["A"]


def test_fetch_missing_local_file_raises_fetch_error(tmp_path) -> None:
    with pytest.raises(FeedFetchError, match="Cannot read feed file"):
        list(RssSource(str(tmp_path / "nope.xml")).fetch())


def test_record_fetch_success_updates_fields(db_session) -> None:
    source = Source(name="s", url="https://x.com/feed")
    db_session.add(source)
    record_fetch_failure(db_session, source, "boom")
    db_session.commit()
    assert source.last_error == "boom"

    record_fetch_success(db_session, source)
    db_session.commit()
    assert source.last_fetched_at is not None
    assert source.last_error is None
    assert source.failure_count == 0
    assert source.is_active is True


def test_record_fetch_failure_deactivates_after_max_failures(db_session) -> None:
    source = Source(name="s")
    db_session.add(source)
    db_session.flush()  # apply column defaults (is_active=True)

    for i in range(1, MAX_FAILURES_BEFORE_INACTIVE):
        record_fetch_failure(db_session, source, f"err {i}")
        assert source.is_active is True

    record_fetch_failure(db_session, source, "final")
    assert source.failure_count == MAX_FAILURES_BEFORE_INACTIVE
    assert source.is_active is False


def test_record_fetch_failure_truncates_long_error(db_session) -> None:
    source = Source(name="s")
    db_session.add(source)
    record_fetch_failure(db_session, source, "x" * 5000)
    assert len(source.last_error) == 1000


def test_active_sources_excludes_inactive(db_session) -> None:
    on = Source(name="on", is_active=True)
    off = Source(name="off", is_active=False)
    db_session.add_all([on, off])
    db_session.commit()

    assert [s.name for s in active_sources(db_session)] == ["on"]


def test_source_defaults_are_active(db_session) -> None:
    db_session.add(Source(name="fresh"))
    db_session.commit()
    source = db_session.scalar(select(Source))
    assert source.is_active is True
    assert source.failure_count == 0
    assert source.last_error is None
    assert source.last_fetched_at is None


class _OkSource(NewsSource):
    name = "ok"

    def fetch(self, limit: int = 50):
        yield from []


class _BadSource(NewsSource):
    name = "bad"

    def fetch(self, limit: int = 50):
        raise FeedFetchError("down")
        yield  # pragma: no cover — make it a generator


def test_aggregator_reports_source_results() -> None:
    results: list[tuple[str, int, str | None]] = []

    def hook(source: NewsSource, count: int, error: Exception | None) -> None:
        results.append((source.name, count, type(error).__name__ if error else None))

    Aggregator([_OkSource(), _BadSource()], on_source_result=hook).collect()

    assert ("ok", 0, None) in results
    assert ("bad", 0, "FeedFetchError") in results


def test_aggregator_survives_failing_hook() -> None:
    def hook(source: NewsSource, count: int, error: Exception | None) -> None:
        raise RuntimeError("hook is broken")

    items = Aggregator([_OkSource()], on_source_result=hook).collect()  # must not raise
    assert items == []
