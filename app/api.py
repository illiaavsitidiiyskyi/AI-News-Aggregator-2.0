"""FastAPI application exposing the aggregator over HTTP."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import uvicorn
from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import __version__
from app.db import get_session
from app.storage import list_items

logger = logging.getLogger(__name__)

app = FastAPI(
    title="AI News Aggregator 2.0",
    version=__version__,
    description="Aggregates AI-related news from multiple sources.",
)


@app.get("/health", tags=["ops"])
def health(session: Session = Depends(get_session)) -> dict[str, str]:
    """Liveness + DB connectivity probe."""
    session.execute(text("SELECT 1"))
    return {
        "status": "ok",
        "database": "ok",
        "version": __version__,
        "time": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/news", tags=["news"])
def news(limit: int = 50, session: Session = Depends(get_session)) -> list[dict]:
    """Return the newest aggregated news items from the database."""
    records = list_items(session, limit=min(limit, 200))
    return [
        {
            "id": r.id,
            "title": r.title,
            "url": r.url,
            "source": r.source,
            "published_at": r.published_at.isoformat() if r.published_at else None,
        }
        for r in records
    ]


def run() -> None:
    """Run the API with uvicorn (used by the ``news-aggregator-api`` script)."""
    uvicorn.run("app.api:app", host="127.0.0.1", port=8000)


if __name__ == "__main__":
    run()
