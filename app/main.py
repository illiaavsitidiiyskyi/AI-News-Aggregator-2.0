"""Entry point: run the aggregation pipeline once or in a loop."""

from __future__ import annotations

import logging
import time

from app.aggregator import Aggregator
from app.config import Config
from app.sources.rss import RssSource

#: Default feeds; extend or replace via configuration later.
DEFAULT_FEEDS = [
    "https://huggingface.co/blog/feed.xml",
    "https://openai.com/news/rss.xml",
]

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def build_aggregator(config: Config) -> Aggregator:
    sources = [RssSource(url) for url in DEFAULT_FEEDS]
    return Aggregator(sources, config)


def run_once(config: Config) -> None:
    items = build_aggregator(config).collect()
    logger.info("Collected %d unique news items", len(items))
    for item in items[:10]:
        logger.info("  [%s] %s", item.source, item.title)


def main() -> None:
    config = Config.from_env()
    while True:
        run_once(config)
        logger.info("Sleeping %d minutes...", config.refresh_interval_minutes)
        time.sleep(config.refresh_interval_minutes * 60)


if __name__ == "__main__":
    main()
