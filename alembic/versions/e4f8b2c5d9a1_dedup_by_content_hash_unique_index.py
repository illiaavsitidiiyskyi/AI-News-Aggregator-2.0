"""dedup articles by content hash unique index

Adds ``articles.content_hash`` (sha256 of title+content) as a second dedup key
with a unique index: it catches the same material syndicated under a different
URL. Backfilled from existing rows; rows sharing a content hash collapse to the
oldest one. NULL (empty content) rows never conflict.

Revision ID: e4f8b2c5d9a1
Revises: a1c9d4e2f7b6
Create Date: 2026-11-03 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e4f8b2c5d9a1'
down_revision: Union[str, Sequence[str], None] = 'a1c9d4e2f7b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _compute_content_hash(title: str, content: str) -> str | None:
    """Frozen copy of ``app.models.compute_content_hash``.

    Migrations must not depend on evolving application code — this backfill has
    to keep producing the same values it did when it first ran.
    """
    import hashlib

    # Stored title/content are already normalized by storage; normalize again
    # only to strip residual whitespace (normalize_text is idempotent).
    title = (title or "").strip()
    content = (content or "").strip()
    if not content:
        return None
    return hashlib.sha256(f"{title}\n{content}".encode("utf-8")).hexdigest()


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('articles', sa.Column('content_hash', sa.String(length=64), nullable=True))

    connection = op.get_bind()
    rows = connection.execute(sa.text("SELECT id, title, content FROM articles")).fetchall()
    for row_id, title, content in rows:
        connection.execute(
            sa.text("UPDATE articles SET content_hash = :value WHERE id = :id"),
            {"value": _compute_content_hash(title, content), "id": row_id},
        )

    # Collapse existing content duplicates (keep the oldest row) so the unique
    # index can be created. NULL hashes are exempt — they never conflict.
    connection.execute(
        sa.text(
            "DELETE FROM articles WHERE content_hash IS NOT NULL AND id NOT IN "
            "(SELECT MIN(id) FROM articles WHERE content_hash IS NOT NULL GROUP BY content_hash)"
        )
    )

    op.create_unique_constraint('uq_articles_content_hash', 'articles', ['content_hash'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('uq_articles_content_hash', 'articles', type_='unique')
    op.drop_column('articles', 'content_hash')
