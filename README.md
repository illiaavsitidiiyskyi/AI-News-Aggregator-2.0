# AI-News-Aggregator-2.0

Aggregates AI-related news from multiple sources (RSS/Atom feeds, APIs), deduplicates and sorts them newest first.

## Project structure

```
.
├── app/
│   ├── __init__.py
│   ├── config.py          # Configuration (env-driven)
│   ├── models.py          # NewsItem domain model
│   ├── aggregator.py      # Fetch → dedupe → sort pipeline
│   ├── api.py             # FastAPI app (GET /health)
│   ├── main.py            # Entry point (run once or loop)
│   └── sources/
│       ├── __init__.py
│       ├── base.py        # NewsSource abstract base class
│       └── rss.py         # RSS/Atom feed source
├── tests/
│   ├── test_aggregator.py
│   └── test_config.py
├── pyproject.toml
├── .gitignore
└── README.md
```

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Usage

Run the aggregation loop (default: every 30 minutes):

```bash
python -m app.main
```

Or via the installed console script:

```bash
news-aggregator
```

## API

Run the HTTP API:

```bash
uvicorn app.api:app --reload
# or
news-aggregator-api
```

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/health` | Liveness probe → `{"status": "ok", "version": ..., "time": ...}` |
| `GET` | `/docs` | Interactive Swagger UI (auto-generated) |

## Configuration

Environment variables (or a `.env` file in the project root):

| Variable | Default | Description |
| --- | --- | --- |
| `REFRESH_INTERVAL_MINUTES` | `30` | Delay between runs in loop mode |
| `MAX_ITEMS_PER_SOURCE` | `50` | Max items fetched per source |
| `OUTPUT_FORMAT` | `json` | Output format (planned) |

## Tests

```bash
pytest
```

## Extending

Add a new source by subclassing `app.sources.base.NewsSource` and implementing `fetch()`:

```python
from app.sources.base import NewsSource
from app.models import NewsItem

class MyApiSource(NewsSource):
    name = "my-api"

    def fetch(self, limit: int = 50):
        ...
        yield NewsItem(title=..., url=..., source=self.name)
```

Then register it in `app/main.py:build_aggregator`.
