"""Tests for the FastAPI application."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app import __version__
from app.api import app

client = TestClient(app)


def test_health_returns_ok() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"] == __version__


def test_health_includes_utc_timestamp() -> None:
    body = client.get("/health").json()
    assert body["time"].endswith("+00:00")
