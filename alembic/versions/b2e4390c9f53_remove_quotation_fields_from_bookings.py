"""remove all quotation fields from bookings

Revision ID: b2e4390c9f53
Revises: 376d7de1025d
Create Date: 2026-06-30 10:59:04.248517
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'b2e4390c9f53'
down_revision: Union[str, Sequence[str], None] = '376d7de1025d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Drop all quotation-related columns from the bookings table
    op.drop_column('bookings', 'quotation_sent_at')
    op.drop_column('bookings', 'share_token_expires_at')
    op.drop_column('bookings', 'share_token')


def downgrade() -> None:
    """Downgrade schema."""
    # Add them back if we ever need to rollback
    op.add_column('bookings', sa.Column('share_token', sa.String(length=36), autoincrement=False, nullable=True))
    op.add_column('bookings', sa.Column('share_token_expires_at', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True))
    op.add_column('bookings', sa.Column('quotation_sent_at', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True))
