"""Create device_statuses table

Revision ID: a1b2c3d4e5f6
Revises: 395003d024e0
Create Date: 2026-05-07 13:58:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '395003d024e0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.create_table(
        'device_statuses',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('device_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('description', sa.String(), nullable=True),

        sa.ForeignKeyConstraint(
            ['device_id'],
            ['devices.id'],
            name='fk_device_statuses_device_id'
        ),
    )

    op.create_index(
        'ix_device_statuses_device_id',
        'device_statuses',
        ['device_id'],
        unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_index(
        'ix_device_statuses_device_id',
        table_name='device_statuses'
    )

    op.drop_table('device_statuses')