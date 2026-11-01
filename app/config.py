"""Application configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"


@dataclass(frozen=True)
class Config:
    """Runtime configuration loaded from environment variables."""

    refresh_interval_minutes: int = 30
    max_items_per_source: int = 50
    output_format: str = "json"
    database_url: str = "postgresql+psycopg://aggregator:aggregator@127.0.0.1:5432/aggregator"
    data_dir: Path = field(default=DATA_DIR)
    #: Feed download timeout in seconds.
    feed_timeout_seconds: float = 10.0
    #: Total attempts per feed fetch (1 = no retries).
    feed_retries: int = 3
    #: Base delay for exponential backoff between retries.
    feed_retry_backoff_seconds: float = 1.0

    @classmethod
    def from_env(cls) -> Config:
        load_dotenv(PROJECT_ROOT / ".env")
        return cls(
            refresh_interval_minutes=int(os.getenv("REFRESH_INTERVAL_MINUTES", "30")),
            max_items_per_source=int(os.getenv("MAX_ITEMS_PER_SOURCE", "50")),
            output_format=os.getenv("OUTPUT_FORMAT", "json"),
            database_url=os.getenv("DATABASE_URL", cls.database_url),
            feed_timeout_seconds=float(os.getenv("FEED_TIMEOUT_SECONDS", "10")),
            feed_retries=max(1, int(os.getenv("FEED_RETRIES", "3"))),
            feed_retry_backoff_seconds=float(os.getenv("FEED_RETRY_BACKOFF_SECONDS", "1.0")),
        )
