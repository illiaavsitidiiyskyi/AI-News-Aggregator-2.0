"""Tests for the FastAPI application."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import __version__
from app.api import app

client = TestClient(app)


@pytest.fixture()
def client_with_db(db_session):
    with TestClient(app) as c:
        yield c


def test_health_returns_ok(client_with_db) -> None:
    response = client_with_db.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["version"] == __version__


def test_health_includes_utc_timestamp(client_with_db) -> None:
    body = client_with_db.get("/health").json()
    assert body["time"].endswith("+00:00")


def test_news_returns_empty_list_by_default(client_with_db) -> None:
    response = client_with_db.get("/news")
    assert response.status_code == 200
    assert response.json() == []
