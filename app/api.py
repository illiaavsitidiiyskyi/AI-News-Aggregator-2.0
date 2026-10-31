"""FastAPI application exposing the aggregator over HTTP."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import uvicorn
from fastapi import FastAPI

from app import __version__

logger = logging.getLogger(__name__)

app = FastAPI(
    title="AI News Aggregator 2.0",
    version=__version__,
    description="Aggregates AI-related news from multiple sources.",
)


@app.get("/health", tags=["ops"])
def health() -> dict[str, str]:
    """Liveness probe: confirms the service is up."""
    return {
        "status": "ok",
        "version": __version__,
        "time": datetime.now(timezone.utc).isoformat(),
    }


def run() -> None:
    """Run the API with uvicorn (used by the ``news-aggregator-api`` script)."""
    uvicorn.run("app.api:app", host="127.0.0.1", port=8000)


if __name__ == "__main__":
    run()
