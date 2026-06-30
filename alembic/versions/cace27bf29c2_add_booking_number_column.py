"""add_booking_number_column

Revision ID: cace27bf29c2
Revises: 42724b5be0af
Create Date: 2026-07-01 12:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'cace27bf29c2'
down_revision: Union[str, Sequence[str], None] = '42724b5be0af'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # 1. Add the column as NULLABLE first so existing rows don't crash
    op.add_column('bookings', sa.Column('booking_number', sa.String(length=20), nullable=True))
    
    # 2. Backfill existing rows with a legacy format (e.g., LEGACY-1, LEGACY-2)
    # This ensures every existing row gets a unique string value.
    op.execute("UPDATE bookings SET booking_number = 'LEGACY-' || id::text WHERE booking_number IS NULL")
    
    # 3. Now that all rows have a value, make the column NOT NULL
    op.alter_column(
        'bookings', 
        'booking_number',
        existing_type=sa.String(length=20),
        nullable=False
    )
    
    # 4. Add the unique constraint/index
    op.create_index(op.f('ix_bookings_booking_number'), 'bookings', ['booking_number'], unique=True)

def downgrade() -> None:
    op.drop_index(op.f('ix_bookings_booking_number'), table_name='bookings')
    op.drop_column('bookings', 'booking_number')
