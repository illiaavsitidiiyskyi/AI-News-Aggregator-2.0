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
    data_dir: Path = field(default=DATA_DIR)

    @classmethod
    def from_env(cls) -> "Config":
        load_dotenv(PROJECT_ROOT / ".env")
        return cls(
            refresh_interval_minutes=int(os.getenv("REFRESH_INTERVAL_MINUTES", "30")),
            max_items_per_source=int(os.getenv("MAX_ITEMS_PER_SOURCE", "50")),
            output_format=os.getenv("OUTPUT_FORMAT", "json"),
        )
