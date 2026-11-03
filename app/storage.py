"""Persistence layer: map domain NewsItem to Source/Article records."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.db_models import Article, Source, utcnow
from app.models import NewsItem, compute_content_hash, normalize_url
from app.normalization import clean_html, normalize_datetime, normalize_text

#: Consecutive failures after which a source is deactivated.
MAX_FAILURES_BEFORE_INACTIVE = 5
#: Cap for stored error messages.
MAX_ERROR_LENGTH = 1000


def get_or_create_source(session: Session, name: str, url: str | None = None) -> Source:
    """Fetch a Source by name or create it on first sight."""
    source = session.scalar(select(Source).where(Source.name == name))
    if source is None:
        source = Source(name=name, url=url)
        session.add(source)
        session.flush()
    return source


def record_fetch_success(session: Session, source: Source) -> None:
    """Mark a source as successfully fetched: stamp time, clear errors, reactivate."""
    source.last_fetched_at = utcnow()
    source.last_error = None
    source.failure_count = 0
    source.is_active = True


def record_fetch_failure(
    session: Session, source: Source, error: str, max_failures: int = MAX_FAILURES_BEFORE_INACTIVE
) -> None:
    """Record a fetch failure; deactivate the source after ``max_failures`` in a row."""
    source.last_error = error[:MAX_ERROR_LENGTH]
    # Column defaults only apply at INSERT; treat a pre-flush object as fresh.
    source.failure_count = (source.failure_count or 0) + 1
    if source.failure_count >= max_failures:
        source.is_active = False


def active_sources(session: Session) -> list[Source]:
    """Return all sources the aggregator should fetch from."""
    return list(session.scalars(select(Source).where(Source.is_active.is_(True))))


def _row_from_item(item: NewsItem, source_id: int) -> dict:
    """Map a NewsItem to an Article row, normalizing text, dates and the dedup keys."""
    url = normalize_text(item.url)
    title = normalize_text(item.title)[:500]
    content = clean_html(item.summary)
    return {
        "title": title,
        "url": url[:1000],
        "normalized_url": normalize_url(url)[:1000],
        "content": content,
        # Hash what is actually stored, so the key always matches the row.
        "content_hash": compute_content_hash(title, content),
        "published_at": normalize_datetime(item.published_at),
        "source_id": source_id,
    }


def save_items(session: Session, items: list[NewsItem]) -> int:
    """Insert items, resolving sources and skipping duplicates.

    Duplicates are decided by the DB via unique constraints: ``normalized_url``
    (same link, cosmetic variants) and ``content_hash`` (same material under a
    different link). Each insert runs in its own savepoint, so a duplicate
    skips only that item and never rolls back rows already added in this batch.
    Returns the number of new rows.
    """
    new_count = 0
    for item in items:
        if not item.url:
            continue
        source = get_or_create_source(session, item.source)
        article = Article(**_row_from_item(item, source.id))
        try:
            with session.begin_nested():
                session.add(article)
                session.flush()
            new_count += 1
        except IntegrityError:
            # Duplicate normalized_url or content_hash: the article is already stored.
            pass
    return new_count


def save_items_upsert(session: Session, items: list[NewsItem]) -> int:
    """Insert items with ON CONFLICT DO NOTHING. Returns the number of new rows.

    No conflict target is given on purpose: there are two unique keys
    (``normalized_url``, ``content_hash``) and PostgreSQL allows a single
    conflict clause per INSERT — an untargeted one covers both.
    """
    rows = []
    for item in items:
        if not item.url:
            continue
        source = get_or_create_source(session, item.source)
        rows.append(_row_from_item(item, source.id))
    if not rows:
        return 0
    stmt = pg_insert(Article).values(rows).on_conflict_do_nothing().returning(Article.id)
    # RETURNING gives an accurate count; rowcount is unreliable for ON CONFLICT DO NOTHING.
    return len(session.execute(stmt).fetchall())


def list_items(session: Session, limit: int = 50) -> list[Article]:
    """Return the newest persisted articles (with their source eagerly loaded)."""
    stmt = (
        select(Article)
        .options(joinedload(Article.source))
        .order_by(Article.published_at.desc().nullslast(), Article.id.desc())
        .limit(limit)
    )
    return list(session.scalars(stmt))
