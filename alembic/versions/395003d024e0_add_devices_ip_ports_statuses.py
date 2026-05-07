"""add devices ip, ports, statuses

Revision ID: 395003d024e0
Revises: f8c2d9e3a1b4
Create Date: 2026-05-07 13:24:12.167384

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '395003d024e0'
down_revision: Union[str, Sequence[str], None] = 'f8c2d9e3a1b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.create_table(
        'device_ports',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('port_number', sa.String(), nullable=False),
        sa.Column('device_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['device_id'], ['devices.id']),
        sa.UniqueConstraint(
            'port_number',
            name='uq_device_ports_port_number'
        )
    )

    op.add_column(
        'devices',
        sa.Column('ip', sa.String(), nullable=True)
    )

    op.alter_column(
        'devices',
        'enabled',
        existing_type=sa.BOOLEAN(),
        server_default=None,
        existing_nullable=False
    )

    op.create_unique_constraint(
        'uq_devices_ip',
        'devices',
        ['ip']
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_constraint(
        'uq_devices_ip',
        'devices',
        type_='unique'
    )

    op.alter_column(
        'devices',
        'enabled',
        existing_type=sa.BOOLEAN(),
        server_default=sa.text('true'),
        existing_nullable=False
    )

    op.drop_column('devices', 'ip')

    op.drop_table('device_ports')