"""add fetch status columns to sources

Revision ID: 9f3a1c2b7d8e
Revises: 5021c188ae29
Create Date: 2026-11-01 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9f3a1c2b7d8e'
down_revision: Union[str, Sequence[str], None] = '5021c188ae29'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('sources', sa.Column('last_fetched_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('sources', sa.Column('last_error', sa.Text(), nullable=True))
    op.add_column('sources', sa.Column('failure_count', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('sources', sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('sources', 'is_active')
    op.drop_column('sources', 'failure_count')
    op.drop_column('sources', 'last_error')
    op.drop_column('sources', 'last_fetched_at')
