"""Shared pytest fixtures: isolated SQLite database for each test."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy.orm import Session

from app.db import get_session_factory, init_db, reset_db_state


@pytest.fixture()
def db_session(tmp_path, monkeypatch) -> Iterator[Session]:
    """Fresh SQLite database per test, wired into the app's session factory."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{tmp_path}/test.db")
    reset_db_state()
    init_db()
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()
        reset_db_state()
