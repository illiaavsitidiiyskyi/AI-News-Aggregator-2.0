# AI-News-Aggregator-2.0

Aggregates AI-related news from multiple sources (RSS/Atom feeds, APIs), deduplicates and sorts them newest first.

## Project structure

```
.
├── app/
│   ├── __init__.py
│   ├── config.py          # Configuration (env-driven)
│   ├── models.py          # NewsItem domain model, dedup keys (URL + content hash)
│   ├── normalization.py   # Date/encoding normalization, HTML → plain text
│   ├── aggregator.py      # Fetch → dedupe (URL + fuzzy titles) → sort pipeline
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
│   ├── test_normalization.py
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
(deduplicated by normalized URL and content hash).

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

## Data normalization

`app/normalization.py` cleans up data at the source boundary (`RssSource`) and again
defensively on save (`app/storage.py`):

- **Dates**: naive datetimes are treated as UTC, aware ones converted to UTC; sorting and
  storage use a single normalized representation.
- **Encodings**: feeds are decoded by feedparser per their XML declaration (UTF-8,
  windows-1251, …); text fields additionally pass through byte decoding (lossy UTF-8),
  Unicode NFC normalization, and stripping of zero-width/control characters.
- **HTML**: descriptions are converted to plain text — tags and `<script>`/`<style>` blocks
  removed, entities unescaped (including double-encoded markup), whitespace collapsed.
  What lands in `articles.content` and in stdout is always plain text.

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

## Deduplication

Three layers, from exact to fuzzy:

1. **Normalized URL** — `articles.normalized_url` (lowercased scheme/host, fragment
   and trailing slash stripped) with a unique index: cosmetic URL variants collapse
   into one article.
2. **Content hash** — `articles.content_hash` = sha256(title + content) with a unique
   index: catches the same material syndicated under a different URL. NULL when
   content is empty — a title alone is too weak a signal (generic titles collide
   across different articles), so such items are deduplicated by URL only; NULLs
   never conflict in a unique index.
3. **Fuzzy titles** — `titles_similar()` (`app/models.py`), applied by the aggregator
   in memory before anything is saved: titles are tokenized (casefolded, split on
   punctuation, words kept whole) and compared by Jaccard similarity
   (`TITLE_SIMILARITY_THRESHOLD = 0.65`), so word order, casing and a trailing
   `| Publisher` suffix do not matter. Titles with different numbers are never
   similar (`GPT-5` vs `GPT-5.2`, `Top 10` vs `Top 5`), nor are empty ones.
   Similarity is not transitive, so it cannot be a unique index — the database
   enforces the exact keys, the aggregator applies the fuzzy one.

The first two keys make the DB the authority on duplicates; the third collapses
similar titles across sources within a collection run.

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

`app/storage.py` provides `save_items` (per-item insert in a savepoint, resolves sources,
skips duplicates by normalized URL / content hash) and `save_items_upsert` (single
`INSERT ... ON CONFLICT DO NOTHING` covering both unique keys).

## Data model

```
sources                     articles
----                        --------
id          PK              id              PK
name        unique          url             as fetched
url                         normalized_url  unique index (dedup key)
created_at                  title
last_fetched_at nullable    content         (text)
last_error   nullable       content_hash    sha256(title + content), unique index (dedup key)
failure_count (int)         published_at    nullable
is_active    (bool)         source_id       FK → sources.id
                            created_at
```

Fetch-status columns on `sources`: `last_fetched_at` / `last_error` track the latest
fetch outcome, `failure_count` counts consecutive failures and `is_active` marks sources
the aggregator should skip (see Failure handling).

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
