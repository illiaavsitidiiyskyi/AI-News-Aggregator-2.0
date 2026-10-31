"""Persistence layer: map domain NewsItem to Source/Article records."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, joinedload

from app.db_models import Article, Source
from app.models import NewsItem, compute_hash


def get_or_create_source(session: Session, name: str, url: str | None = None) -> Source:
    """Fetch a Source by name or create it on first sight."""
    source = session.scalar(select(Source).where(Source.name == name))
    if source is None:
        source = Source(name=name, url=url)
        session.add(source)
        session.flush()
    return source


def save_items(session: Session, items: list[NewsItem]) -> int:
    """Insert items, resolving sources and skipping duplicates by URL/hash.

    Returns the number of new rows.
    """
    new_count = 0
    for item in items:
        if not item.url:
            continue
        source = get_or_create_source(session, item.source)
        article = Article(
            title=item.title[:500],
            url=item.url[:1000],
            content=item.summary,
            published_at=item.published_at,
            hash=compute_hash(item.url),
            source_id=source.id,
        )
        session.add(article)
        try:
            session.flush()
            new_count += 1
        except Exception:
            # Unique violation (duplicate URL/hash) or transient DB error: skip item.
            session.rollback()
    return new_count


def save_items_upsert(session: Session, items: list[NewsItem]) -> int:
    """Insert items with ON CONFLICT (hash) DO NOTHING. Returns the number of new rows."""
    rows = []
    for item in items:
        if not item.url:
            continue
        source = get_or_create_source(session, item.source)
        rows.append(
            {
                "title": item.title[:500],
                "url": item.url[:1000],
                "content": item.summary,
                "published_at": item.published_at,
                "hash": compute_hash(item.url),
                "source_id": source.id,
            }
        )
    if not rows:
        return 0
    stmt = (
        pg_insert(Article)
        .values(rows)
        .on_conflict_do_nothing(index_elements=["hash"])
        .returning(Article.id)
    )
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
