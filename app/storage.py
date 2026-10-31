"""Persistence layer: map domain NewsItem to DB records."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.db_models import NewsItemRecord
from app.models import NewsItem


def save_items(session: Session, items: list[NewsItem]) -> int:
    """Insert items, skipping duplicates by URL. Returns the number of new rows."""
    new_count = 0
    for item in items:
        if not item.url:
            continue
        record = NewsItemRecord(
            title=item.title[:500],
            url=item.url[:1000],
            source=item.source[:200],
            published_at=item.published_at,
            summary=item.summary,
        )
        session.add(record)
        try:
            session.flush()
            new_count += 1
        except Exception:
            # Unique violation (duplicate URL) or transient DB error: skip item.
            session.rollback()
    return new_count


def save_items_upsert(session: Session, items: list[NewsItem]) -> int:
    """Insert items with ON CONFLICT (url) DO NOTHING. Returns the number of new rows."""
    rows = [
        {
            "title": item.title[:500],
            "url": item.url[:1000],
            "source": item.source[:200],
            "published_at": item.published_at,
            "summary": item.summary,
        }
        for item in items
        if item.url
    ]
    if not rows:
        return 0
    stmt = (
        pg_insert(NewsItemRecord)
        .values(rows)
        .on_conflict_do_nothing(index_elements=["url"])
        .returning(NewsItemRecord.id)
    )
    # RETURNING gives an accurate count; rowcount is unreliable for ON CONFLICT DO NOTHING.
    return len(session.execute(stmt).fetchall())


def list_items(session: Session, limit: int = 50) -> list[NewsItemRecord]:
    """Return the newest persisted items."""
    stmt = (
        select(NewsItemRecord)
        .order_by(NewsItemRecord.published_at.desc().nullslast(), NewsItemRecord.id.desc())
        .limit(limit)
    )
    return list(session.scalars(stmt))
