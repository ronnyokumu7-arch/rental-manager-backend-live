"""create_quotations_table

Revision ID: 6daa089eab92
Revises: b2e4390c9f53
Create Date: 2026-06-30 11:15:16.142568

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '6daa089eab92'
down_revision: Union[str, Sequence[str], None] = 'b2e4390c9f53'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('quotations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('client_id', sa.Integer(), nullable=False),
    sa.Column('vehicle_id', sa.Integer(), nullable=False),
    sa.Column('quotation_number', sa.String(), nullable=False),
    sa.Column('valid_until', sa.DateTime(timezone=True), nullable=False),
    sa.Column('status', sa.Enum('draft', 'sent', 'accepted', 'rejected', 'expired', name='quotationstatus'), nullable=False, server_default='draft'),
    sa.Column('start_date', sa.Date(), nullable=False),
    sa.Column('end_date', sa.Date(), nullable=False),
    sa.Column('total_amount', sa.Integer(), nullable=False),
    sa.Column('currency_code', sa.String(length=3), nullable=False, server_default='KES'),
    sa.Column('share_token', sa.String(length=36), nullable=True),
    sa.Column('share_token_expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('booking_id', sa.Integer(), nullable=True),
    sa.Column('converted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    sa.ForeignKeyConstraint(['booking_id'], ['bookings.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['vehicle_id'], ['vehicles.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_quotations_booking_id'), 'quotations', ['booking_id'], unique=False)
    op.create_index(op.f('ix_quotations_client_id'), 'quotations', ['client_id'], unique=False)
    op.create_index(op.f('ix_quotations_id'), 'quotations', ['id'], unique=False)
    op.create_index(op.f('ix_quotations_quotation_number'), 'quotations', ['quotation_number'], unique=True)
    op.create_index(op.f('ix_quotations_share_token'), 'quotations', ['share_token'], unique=True)
    op.create_index(op.f('ix_quotations_tenant_id'), 'quotations', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_quotations_vehicle_id'), 'quotations', ['vehicle_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_quotations_vehicle_id'), table_name='quotations')
    op.drop_index(op.f('ix_quotations_tenant_id'), table_name='quotations')
    op.drop_index(op.f('ix_quotations_share_token'), table_name='quotations')
    op.drop_index(op.f('ix_quotations_quotation_number'), table_name='quotations')
    op.drop_index(op.f('ix_quotations_id'), table_name='quotations')
    op.drop_index(op.f('ix_quotations_client_id'), table_name='quotations')
    op.drop_index(op.f('ix_quotations_booking_id'), table_name='quotations')
    op.drop_table('quotations')
