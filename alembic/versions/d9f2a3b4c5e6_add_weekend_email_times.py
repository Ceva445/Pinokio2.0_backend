"""Add separate email send times for Saturday and Sunday

Revision ID: d9f2a3b4c5e6
Revises: c8e1f2a3b4d5
Create Date: 2026-08-31 10:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd9f2a3b4c5e6'
down_revision: Union[str, Sequence[str], None] = 'c8e1f2a3b4d5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'system_config',
        sa.Column(
            'email_send_times_saturday',
            sa.String(),
            nullable=False,
            server_default='09:00,15:00',
        ),
    )
    op.add_column(
        'system_config',
        sa.Column(
            'email_send_times_sunday',
            sa.String(),
            nullable=False,
            server_default='09:00,15:00',
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('system_config', 'email_send_times_sunday')
    op.drop_column('system_config', 'email_send_times_saturday')
