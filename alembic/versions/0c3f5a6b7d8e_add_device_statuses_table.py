"""Add device statuses table

Revision ID: 0c3f5a6b7d8e
Revises: f8c2d9e3a1b4
Create Date: 2026-05-06 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0c3f5a6b7d8e'
down_revision: Union[str, Sequence[str], None] = 'f8c2d9e3a1b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create device_statuses table (ENUM створиться автоматично)
    op.create_table(
        'device_statuses',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('device_id', sa.Integer(), nullable=False),
        sa.Column(
            'status',
            sa.Enum(
                'work', 'service', 'wanted', 'old_wanted', 'kantor',
                name='device_status_type'
            ),
            nullable=False
        ),
        sa.Column('description', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['device_id'], ['devices.id']),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_index(
        op.f('ix_device_statuses_device_id'),
        'device_statuses',
        ['device_id'],
        unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_device_statuses_device_id'), table_name='device_statuses')
    op.drop_table('device_statuses')
    sa.Enum(name='device_status_type').drop(op.get_bind(), checkfirst=True)
