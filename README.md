# AI-News-Aggregator-2.0

Aggregates AI-related news from multiple sources (RSS/Atom feeds, APIs), deduplicates and sorts them newest first.

## Project structure

```
.
├── app/
│   ├── __init__.py
│   ├── config.py          # Configuration (env-driven)
│   ├── models.py          # NewsItem domain model, URL normalization + hashing
│   ├── aggregator.py      # Fetch → dedupe → sort pipeline
│   ├── api.py             # FastAPI app (GET /health, GET /news)
│   ├── db.py              # SQLAlchemy engine/session/Base
│   ├── db_models.py       # ORM models: Source, Article
│   ├── storage.py         # Persistence: save/list items
│   ├── main.py            # Entry point (run once or loop)
│   ├── rss_reader.py      # Standalone service: read one feed, print articles
│   └── sources/
│       ├── __init__.py
│       ├── base.py        # NewsSource abstract base class
│       └── rss.py         # RSS/Atom feed source
├── tests/
│   ├── conftest.py        # SQLite-per-test fixture
│   ├── test_aggregator.py
│   ├── test_api.py
│   ├── test_config.py
│   ├── test_failure_handling.py
│   ├── test_rss_reader.py
│   └── test_storage.py
├── alembic/               # Migrations (versions/, env.py)
├── alembic.ini
├── docker-compose.yml     # PostgreSQL 16 for local development
├── pyproject.toml
├── .env.example
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

### Print articles from a single feed

`app/rss_reader.py` is a standalone service that reads one RSS/Atom feed via `feedparser`,
prints its articles to stdout and saves them to the database: the feed is registered in the
`sources` table (name = feed title, url = feed URL), each article in `articles`
(deduplicated by URL hash).

```bash
python -m app.rss_reader                              # default Hugging Face blog feed
python -m app.rss_reader <FEED_URL> --limit 10        # custom feed, at most 10 articles
python -m app.rss_reader <FEED_URL> --no-save         # only print, do not touch the DB
# or
news-feed-reader <FEED_URL>
```

Example output:

```
1. Some article title
   https://example.com/article
   2026-10-30 17:57
   Plain-text summary with HTML stripped.

Saved 1 new article(s) to the database.
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
| `GET` | `/health` | Liveness + DB connectivity probe |
| `GET` | `/news` | Newest aggregated news items from the DB (`?limit=50`) |
| `GET` | `/docs` | Interactive Swagger UI (auto-generated) |

## Configuration

Environment variables (or a `.env` file in the project root):

| Variable | Default | Description |
| --- | --- | --- |
| `REFRESH_INTERVAL_MINUTES` | `30` | Delay between runs in loop mode |
| `MAX_ITEMS_PER_SOURCE` | `50` | Max items fetched per source |
| `OUTPUT_FORMAT` | `json` | Output format (planned) |
| `DATABASE_URL` | `postgresql+psycopg://aggregator:aggregator@127.0.0.1:5432/aggregator` | SQLAlchemy database URL |
| `FEED_TIMEOUT_SECONDS` | `10` | Feed download timeout |
| `FEED_RETRIES` | `3` | Total attempts per feed fetch (1 = no retries) |
| `FEED_RETRY_BACKOFF_SECONDS` | `1.0` | Base delay for exponential backoff between retries |

## Failure handling

- **Timeouts & retries**: feed downloads use a configurable timeout and are retried with
  exponential backoff (`FEED_RETRIES` / `FEED_RETRY_BACKOFF_SECONDS`). HTTP 4xx errors are
  not retried; 429/5xx and network errors are.
- **Broken feeds**: unrecoverably malformed XML raises `FeedParseError` (`app/sources/rss.py`);
  partially broken feeds that still yield entries are logged as warnings and processed.
- **Source status**: each fetch outcome is recorded on the source row —
  `last_fetched_at`, `last_error`, `failure_count`, `is_active`. A source is deactivated
  (`is_active = false`) after 5 consecutive failures and skipped by the aggregator until
  it is manually re-enabled; a successful fetch resets the counters and reactivates it.
- **Logging**: fetch retries, per-source results and failures are logged; the aggregation
  loop survives a failed cycle and retries on the next interval.

## Database

PostgreSQL for local development (SQLAlchemy 2.0 + psycopg 3):

```bash
cp .env.example .env
docker compose up -d       # start PostgreSQL 16 on port 5432
alembic upgrade head       # apply migrations
```

### Migrations (Alembic)

The schema is managed by Alembic; `env.py` reads `DATABASE_URL` from the app config
(so `.env` works) and uses `app.db.Base.metadata` for autogeneration.

```bash
alembic revision --autogenerate -m "describe change"   # generate a migration
alembic upgrade head                                   # apply
alembic downgrade -1                                   # roll back one revision
alembic current                                        # show current revision
```

For tests, tables are created directly from the models (`init_db()` in `tests/conftest.py`);
Alembic is used for the dev/prod database.

`app/storage.py` provides `save_items` (per-item insert, resolves sources, skips duplicates by
URL/hash) and `save_items_upsert` (single `INSERT ... ON CONFLICT (hash) DO NOTHING`).

## Data model

```
sources                     articles
----                        --------
id          PK              id           PK
name        unique          url          unique
url                         title
created_at                  content      (text)
last_fetched_at nullable    published_at nullable
last_error   nullable       hash         sha256(normalized url), unique, indexed
failure_count (int)         source_id    FK → sources.id
is_active    (bool)         created_at
```

Fetch-status columns on `sources`: `last_fetched_at` / `last_error` track the latest
fetch outcome, `failure_count` counts consecutive failures and `is_active` marks sources
the aggregator should skip (see Failure handling).

Deduplication is based on `hash` — the sha256 of the normalized URL (lowercased scheme/host,
fragment and trailing slash stripped), so cosmetic URL variants collapse into one article.

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
