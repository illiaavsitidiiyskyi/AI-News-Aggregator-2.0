"""SQLAlchemy ORM models: Source and Article."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now().astimezone()


class Source(Base):
    """A news source — RSS feed, API, scraper, etc. (table ``sources``)."""

    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    #: Fetch-status fields (failure handling).
    last_fetched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    #: Last fetch/parse error message, cleared on the next successful fetch.
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Consecutive failures; reset to 0 on success. Used to flip ``is_active``.
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: Inactive sources are skipped by the aggregator until manually re-enabled.
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    articles: Mapped[list[Article]] = relationship(back_populates="source")

    def __repr__(self) -> str:
        return f"<Source {self.name} active={self.is_active}>"


class Article(Base):
    """A single aggregated news article (table ``articles``)."""

    __tablename__ = "articles"
    __table_args__ = (
        UniqueConstraint("url", name="uq_articles_url"),
        UniqueConstraint("hash", name="uq_articles_hash"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    #: sha256 hex of the normalized URL — dedup key across sources.
    hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    source: Mapped[Source] = relationship(back_populates="articles")

    def __repr__(self) -> str:
        return f"<Article {self.title[:40]!r}>"
