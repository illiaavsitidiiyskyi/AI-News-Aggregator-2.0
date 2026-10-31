"""Tests for configuration loading."""

from __future__ import annotations

from app.config import Config


def test_defaults() -> None:
    config = Config()
    assert config.refresh_interval_minutes == 30
    assert config.max_items_per_source == 50
    assert config.output_format == "json"


def test_from_env_uses_overrides(monkeypatch) -> None:
    monkeypatch.setenv("REFRESH_INTERVAL_MINUTES", "5")
    monkeypatch.setenv("MAX_ITEMS_PER_SOURCE", "10")
    monkeypatch.setenv("OUTPUT_FORMAT", "sqlite")
    config = Config.from_env()
    assert config.refresh_interval_minutes == 5
    assert config.max_items_per_source == 10
    assert config.output_format == "sqlite"
