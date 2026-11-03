"""dedup articles by normalized url unique index

Adds ``articles.normalized_url`` as the dedup key with a unique index,
backfills it from existing ``url`` values, then drops the now-redundant
``hash`` column (and its constraints) and the raw-URL unique constraint.

Revision ID: a1c9d4e2f7b6
Revises: 9f3a1c2b7d8e
Create Date: 2026-11-03 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1c9d4e2f7b6'
down_revision: Union[str, Sequence[str], None] = '9f3a1c2b7d8e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _normalize_url(url: str) -> str:
    """Frozen copy of ``app.models.normalize_url``.

    Migrations must not depend on evolving application code — this backfill has
    to keep producing the same values it did when it first ran.
    """
    from urllib.parse import urlsplit, urlunsplit

    parts = urlsplit((url or "").strip())
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, parts.query, ""))


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('articles', sa.Column('normalized_url', sa.String(length=1000), nullable=True))

    # Backfill from stored URLs, then collapse any duplicates (keep the oldest row)
    # so the unique index can be created. Duplicates should not exist — the old
    # unique ``hash`` was sha256 of the same normalized URL — but be defensive.
    connection = op.get_bind()
    rows = connection.execute(sa.text("SELECT id, url FROM articles")).fetchall()
    for row_id, url in rows:
        connection.execute(
            sa.text("UPDATE articles SET normalized_url = :value WHERE id = :id"),
            {"value": _normalize_url(url), "id": row_id},
        )
    connection.execute(
        sa.text(
            "DELETE FROM articles WHERE id NOT IN "
            "(SELECT MIN(id) FROM articles GROUP BY normalized_url)"
        )
    )
    connection.execute(
        sa.text("UPDATE articles SET normalized_url = '' WHERE normalized_url IS NULL")
    )

    op.alter_column(
        'articles', 'normalized_url',
        existing_type=sa.String(length=1000), nullable=False,
    )
    op.create_unique_constraint('uq_articles_normalized_url', 'articles', ['normalized_url'])

    # Drop the superseded dedup key and the redundant raw-URL uniqueness.
    op.drop_constraint('uq_articles_hash', 'articles', type_='unique')
    op.drop_constraint('uq_articles_url', 'articles', type_='unique')
    op.drop_index('ix_articles_hash', table_name='articles')
    op.drop_column('articles', 'hash')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column('articles', sa.Column('hash', sa.String(length=64), nullable=True))

    # sha256(normalized_url) reproduces the original hash values exactly:
    # hash was defined as sha256 of the normalized URL.
    import hashlib

    connection = op.get_bind()
    rows = connection.execute(sa.text("SELECT id, normalized_url FROM articles")).fetchall()
    for row_id, normalized_url in rows:
        digest = hashlib.sha256((normalized_url or "").encode("utf-8")).hexdigest()
        connection.execute(
            sa.text("UPDATE articles SET hash = :hash WHERE id = :id"),
            {"hash": digest, "id": row_id},
        )
    connection.execute(sa.text("UPDATE articles SET hash = '' WHERE hash IS NULL"))
    op.alter_column('articles', 'hash', existing_type=sa.String(length=64), nullable=False)

    op.create_index(op.f('ix_articles_hash'), 'articles', ['hash'], unique=False)
    op.create_unique_constraint('uq_articles_hash', 'articles', ['hash'])
    op.create_unique_constraint('uq_articles_url', 'articles', ['url'])
    op.drop_constraint('uq_articles_normalized_url', 'articles', type_='unique')
    op.drop_column('articles', 'normalized_url')
