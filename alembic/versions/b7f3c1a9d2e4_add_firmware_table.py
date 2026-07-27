"""Add firmware table (OTA)

Revision ID: b7f3c1a9d2e4
Revises: 7d65862e7068
Create Date: 2026-07-24 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7f3c1a9d2e4'
down_revision: Union[str, Sequence[str], None] = '7d65862e7068'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'firmware',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('version', sa.String(length=64), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column('size', sa.Integer(), nullable=False),
        sa.Column('content_type', sa.String(length=128), nullable=False),
        sa.Column('storage_name', sa.String(length=255), nullable=False),
        sa.Column('sha256', sa.String(length=64), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('uploaded_by', sa.String(length=255), nullable=True),
        sa.Column('uploaded_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_firmware_is_active', 'firmware', ['is_active'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_firmware_is_active', table_name='firmware')
    op.drop_table('firmware')
