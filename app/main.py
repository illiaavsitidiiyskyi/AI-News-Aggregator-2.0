"""Entry point: run the aggregation pipeline once or in a loop."""

from __future__ import annotations

import logging
import time

from sqlalchemy import select

from app.aggregator import Aggregator
from app.config import Config
from app.db import get_session_factory
from app.db_models import Source
from app.sources.base import NewsSource
from app.sources.rss import RssSource
from app.storage import record_fetch_failure, record_fetch_success, save_items

#: Default feeds; extend or replace via configuration later.
DEFAULT_FEEDS = [
    "https://huggingface.co/blog/feed.xml",
    "https://openai.com/news/rss.xml",
]

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def build_source(url: str, config: Config) -> RssSource:
    return RssSource(
        url,
        timeout=config.feed_timeout_seconds,
        retries=config.feed_retries,
        backoff_seconds=config.feed_retry_backoff_seconds,
    )


def inactive_feed_urls() -> set[str]:
    """Feeds whose source was deactivated after repeated failures."""
    session = get_session_factory()()
    try:
        rows = session.scalars(select(Source).where(Source.is_active.is_(False))).all()
        return {row.url for row in rows if row.url}
    finally:
        session.close()


def record_source_result(source: NewsSource, count: int, error: Exception | None) -> None:
    """Persist fetch outcome (last_fetched_at / last_error / is_active). Best-effort."""
    session = get_session_factory()()
    try:
        row = session.scalar(select(Source).where(Source.name == source.name))
        if row is None:
            if error is not None:
                # Don't create rows for failing unknown sources.
                return
            row = Source(name=source.name, url=getattr(source, "url", None))
            session.add(row)
        if error is None:
            record_fetch_success(session, row)
            logger.info("Source %s: fetched %d items", source.name, count)
        else:
            record_fetch_failure(session, row, str(error))
            logger.warning(
                "Source %s: fetch failed (%d consecutive failures, active=%s): %s",
                source.name,
                row.failure_count,
                row.is_active,
                error,
            )
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("Failed to record fetch outcome for source %s", source.name)
    finally:
        session.close()


def build_aggregator(config: Config) -> Aggregator:
    skip = inactive_feed_urls()
    if skip:
        logger.info("Skipping %d inactive source(s): %s", len(skip), ", ".join(sorted(skip)))
    sources = [build_source(url, config) for url in DEFAULT_FEEDS if url not in skip]
    return Aggregator(sources, config, on_source_result=record_source_result)


def run_once(config: Config) -> None:
    items = build_aggregator(config).collect()
    logger.info("Collected %d unique news items", len(items))
    session = get_session_factory()()
    try:
        saved = save_items(session, items)
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("Failed to save items to the database")
        raise
    finally:
        session.close()
    logger.info("Saved %d new articles", saved)
    for item in items[:10]:
        logger.info("  [%s] %s", item.source, item.title)


def main() -> None:
    config = Config.from_env()
    while True:
        try:
            run_once(config)
        except Exception:
            # One failed cycle shouldn't kill the loop; statuses are recorded per source.
            logger.exception("Aggregation cycle failed; will retry after the interval")
        logger.info("Sleeping %d minutes...", config.refresh_interval_minutes)
        time.sleep(config.refresh_interval_minutes * 60)


if __name__ == "__main__":
    main()
